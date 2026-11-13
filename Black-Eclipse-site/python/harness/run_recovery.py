"""Recovery helpers for runs orphaned by a process restart.

The runtime executes agent runs in-process, so a run row left `created`/`running`
by a previous process can never finish: no task will ever complete it and a
client streaming it would wait forever. ``fail_orphaned_runs`` therefore
reconciles each one to a terminal or recoverable state with a durable event:

  * an approval wait  -> `failed` (`RUN_INTERRUPTED`): the wait was lost;
  * a checkpoint       -> `interrupted` (`RUN_INTERRUPTED`): resumable through
    `POST /runs/{id}/resume`;
  * no checkpoint      -> `failed` (`RUN_ORPHANED`): nothing to resume.

The update is conditional (`status IN ('created','running')`) so a live worker
that advanced the row is never overwritten. It uses the store's ONE shared
connection, exactly like the other per-subsystem stores under `harness/`.
"""

from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Optional

from .persistence import new_id, now_iso

# A run whose LAST event is one of these was blocked on the OPERATOR, not on
# model progress — it was paused on an approval card. A restart still cannot
# resume it (the in-process task is gone), so it is failed, but honestly labeled
# as an interruption-while-waiting so the operator knows nothing was applied.
APPROVAL_WAIT_EVENTS = frozenset({"approval.requested", "user.approval.required"})
INTERRUPTED_CODE = "RUN_INTERRUPTED"
INTERRUPTED_MESSAGE = (
    "the runtime restarted while this run was waiting for your approval; "
    "nothing was applied — re-request the action"
)


def _last_event_type(db: Any, run_id: str) -> str:
    row = db.execute(
        "SELECT type FROM HarnessEvent WHERE runId = ? ORDER BY seq DESC LIMIT 1", (run_id,)
    ).fetchone()
    return str(row["type"] or "") if row is not None else ""


def _has_checkpoint(db: Any, run_id: str) -> bool:
    try:
        row = db.execute(
            "SELECT 1 AS present FROM RunCheckpoint WHERE runId = ? LIMIT 1", (run_id,)
        ).fetchone()
    except Exception:  # noqa: BLE001 - a missing table means nothing to resume
        return False
    return row is not None


def _lease_is_live(db: Any, run_id: str) -> bool:
    """Whether a live runtime currently owns this run (do not touch it)."""
    try:
        row = db.execute(
            "SELECT expiresAtMs FROM RunLease WHERE runId = ?", (run_id,)
        ).fetchone()
    except Exception:  # noqa: BLE001 - no lease table means no live owner
        return False
    return bool(row and int(row["expiresAtMs"]) >= int(time.time() * 1000))


def fail_orphaned_runs(
    store: Any, reason: str, *, environment: Optional[str] = None
) -> int:
    """Reconcile non-terminal runs left behind by a previous process.

    A run paused on an operator approval is `failed` with `RUN_INTERRUPTED`: the
    wait was lost and nothing was applied. A run that HAS a durable checkpoint is
    `interrupted` — a recoverable state the resume endpoint accepts. Only a run
    with nothing to resume is terminal `RUN_ORPHANED` (there is genuinely no work
    to recover). The update is conditional, so a run that a live worker has
    already advanced is never overwritten.

    A run with a **live lease** is skipped entirely: another runtime is executing
    it. When `environment` is supplied, a run explicitly owned by a different
    environment is also skipped.

    Idempotent (a second pass finds nothing) and safe to call on every boot.
    """
    db = store._db  # noqa: SLF001 - the one shared connection
    columns = {row["name"] for row in db.execute("PRAGMA table_info(HarnessRun)").fetchall()}
    select_env = "environment" if "environment" in columns else "NULL AS environment"
    rows = db.execute(
        f"SELECT id, {select_env} FROM HarnessRun WHERE status IN ('created', 'running')"
    ).fetchall()
    reconciled = 0
    for row in rows:
        run_id = row["id"]
        if _lease_is_live(db, run_id):
            continue  # a live runtime owns it; never orphan it
        run_environment = row["environment"] if "environment" in row.keys() else None
        if environment and run_environment and run_environment != environment:
            continue  # another environment's run; not ours to reconcile
        now = now_iso()
        if _last_event_type(db, run_id) in APPROVAL_WAIT_EVENTS:
            status, code, message, event_type = (
                "failed", INTERRUPTED_CODE, INTERRUPTED_MESSAGE, "run.failed",
            )
        elif _has_checkpoint(db, run_id):
            status, code, message, event_type = (
                "interrupted",
                "RUN_INTERRUPTED",
                "the agent runtime restarted while this run was in flight; "
                "a checkpoint exists and the run can be resumed",
                "run.interrupted",
            )
        else:
            status, code, message, event_type = (
                "failed", "RUN_ORPHANED", reason, "run.failed",
            )
        error = json.dumps({"code": code, "message": message})
        cursor = db.execute(
            "UPDATE HarnessRun SET status = ?, error = ?, updatedAt = ?, finishedAt = ? "
            "WHERE id = ? AND status IN ('created', 'running')",
            (status, error, now, now, run_id),
        )
        if cursor.rowcount == 0:
            # A live worker advanced this row between the SELECT and the UPDATE.
            continue
        db.commit()
        try:
            from .event_sequence import get_event_sequence  # noqa: PLC0415

            sequence = get_event_sequence(store)
            if sequence is not None:
                sequence.append(run_id, event_type, json.loads(error))
            else:  # pragma: no cover - only a non-sqlite stub reaches this
                max_seq = db.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS s FROM HarnessEvent WHERE runId = ?",
                    (run_id,),
                ).fetchone()["s"]
                db.execute(
                    "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (new_id("evt"), run_id, event_type, max_seq + 1, now, error),
                )
                db.commit()
        except Exception:  # noqa: BLE001 - the run state is already reconciled
            log.warning("failed to append recovery event for %s", run_id, exc_info=True)
        reconciled += 1
    return reconciled


def _runtime_port_is_free() -> bool:
    """Whether the runtime's bind port is still available to this process.

    FastAPI runs the lifespan (and therefore this reconciliation) BEFORE uvicorn
    binds the socket. A runtime that has ALREADY bound the port is a live,
    serving instance — a second process that boots against the same port will
    fail to bind and die moments later, but only after its lifespan ran. If that
    second process reconciled, it would fail the very runs the live instance is
    executing (`RUN_ORPHANED`). So we reconcile only when the port is free, i.e.
    this process is the one that will own the runtime.
    """
    host = os.environ.get("HARNESS_PY_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("HARNESS_PY_PORT", "8765"))
    except (TypeError, ValueError):
        port = 8765
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # No SO_REUSEADDR: on Windows that would let the probe "succeed" on a
        # port another process is actively listening on, defeating the check.
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def is_context_overflow(error: Optional[dict[str, Any]]) -> bool:
    """True when the failure is the model's context window, not a bad request."""
    return bool(error) and error.get("code") == "CONTEXT_OVERFLOW"


async def recover_overflow_state(
    store: Any, run_id: str, emitter: Any, invoke: Any, final_state: dict[str, Any],
    *, window: Optional[int] = None, max_chars: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """One safe checkpoint retry for a step>1 context overflow.

    A tool-bearing run is recoverable from a completed-work checkpoint because
    the checkpoint already contains every tool result and the effect ledger
    refuses a run with an unconfirmed effect. The idempotency ledger remains the
    second guard: a replayed call reuses its recorded result.

    `max_chars` (the tighter budget's history allowance) bounds the rebuilt
    prompt: after pruning, the oldest units are removed until the prompt fits,
    never the system head, the last user turn, or an assistant/tool pair.
    """
    recovered = recoverable_state(store, run_id)
    if not recovered:
        return None
    from .context.compression_ladder import compress  # noqa: PLC0415

    original = list(recovered.get("messages") or [])
    ladder = await compress(original, budget=None, request=None, emitter=emitter)
    messages = (
        ladder.messages
        if ladder.ok and ladder.stage in ("prune", "summary", "skeleton")
        else original
    )
    if max_chars is not None:
        messages = _trim_to_chars(messages, int(max_chars))
    recovered["messages"] = messages
    kept_turns = sum(
        1 for m in messages if str(getattr(m, "type", "") or "") in ("human", "ai")
    )
    try:
        await emitter.emit("context.recovered", {
            "reason": "context_overflow",
            "step": int(final_state.get("step") or 0),
            "fromStep": int(recovered.get("step") or 0),
            "prunedToolResults": ladder.pruned_tool_results,
            "keptTurns": kept_turns,
            "window": window,
            "stage": ladder.stage,
        })
    except Exception:  # noqa: BLE001
        pass
    return await invoke([], "", recovered)


SAFE_RECOVERY_KINDS = ("tool_results", "replan")


def _trim_to_chars(messages: list[Any], max_chars: int) -> list[Any]:
    """Drop the oldest whole units until the rebuilt prompt fits `max_chars`.

    Never removes the stable system head, the last user turn, or half of an
    assistant/tool pair. A prompt that cannot be reduced further is returned
    as-is (the caller's honest overflow stands).
    """
    from .context.compression_ladder import protect_tail  # noqa: PLC0415

    out = list(messages or [])
    limit = max(1, int(max_chars))
    for _ in range(len(out)):
        total = sum(len(str(getattr(m, "content", "") or "")) for m in out)
        if total <= limit:
            break
        head_end = 0
        while head_end < len(out) and str(getattr(out[head_end], "type", "") or "") == "system":
            head_end += 1
        cut = protect_tail(out, turns=4, tool_results=4)
        if cut <= head_end:
            break
        del out[head_end:cut]
    return out

def recoverable_state(
    store: Any, run_id: str, *, kinds: tuple[str, ...] = SAFE_RECOVERY_KINDS,
) -> Optional[dict[str, Any]]:
    """A checkpoint-derived graph state when recovery is safe, else None.

    Requires a checkpoint at a completed-work boundary (`tool_results` or
    `replan`), a durable message cursor (or legacy tail), and no unconfirmed
    effect. A boundary checkpoint means every issued tool call already has a
    durable result, so rebuilding cannot re-issue it; the effect ledger catches
    the in-flight case.
    """
    try:
        from .run_effects import RunEffects  # noqa: PLC0415
        from .run_lineage import RunLineage  # noqa: PLC0415

        if RunEffects(store).has_unconfirmed(run_id):
            return None
        lineage = RunLineage(store)
        checkpoint = lineage.latest_checkpoint(run_id)
        if checkpoint is None:
            return None
        if kinds and str(checkpoint.get("kind") or "") not in kinds:
            return None
        payload = checkpoint.get("payload") or {}
        restored = None
        if payload.get("messageSeq") is not None:
            restored = lineage.load_messages(run_id) or None
        if restored is None:
            from .checkpoint_io import restore_messages  # noqa: PLC0415

            restored = restore_messages(payload.get("messages") or [])
        if not restored:
            return None
        state: dict[str, Any] = {
            "messages": restored,
            "step": int(payload.get("step", 0)),
            "tool_calls": int(payload.get("toolCalls", 0)),
            "tool_errors": int(payload.get("toolErrors", 0)),
            "replans": int(payload.get("replans", 0)),
            "prompt_tokens": int(payload.get("promptTokens", 0)),
            "completion_tokens": int(payload.get("completionTokens", 0)),
            "final": None,
        }
        if payload.get("stepId"):
            state["plan_step_id"] = payload["stepId"]
        return state
    except Exception:  # noqa: BLE001 - recovery is best-effort
        return None


def reconcile_orphaned_runs(
    store: Any, reason: str, *, environment: Optional[str] = None
) -> dict[str, Any]:
    """Fail/recover runs left by a dead process — but only when this process owns
    the runtime port. Returns a small report; never raises."""
    if not _runtime_port_is_free():
        return {"failed": 0, "skipped": "another runtime is already serving this port"}
    return {"failed": fail_orphaned_runs(store, reason, environment=environment)}


__all__ = ["fail_orphaned_runs", "reconcile_orphaned_runs"]
