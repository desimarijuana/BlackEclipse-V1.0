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
from typing import Any

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


def fail_orphaned_runs(store: Any, reason: str) -> int:
    """Reconcile non-terminal runs left behind by a previous process.

    A run paused on an operator approval is `failed` with `RUN_INTERRUPTED`: the
    wait was lost and nothing was applied. A run that HAS a durable checkpoint is
    `interrupted` — a recoverable state the resume endpoint accepts. Only a run
    with nothing to resume is terminal `RUN_ORPHANED` (there is genuinely no work
    to recover). The update is conditional, so a run that a live worker has
    already advanced is never overwritten.

    Idempotent (a second pass finds nothing) and safe to call on every boot.
    """
    db = store._db  # noqa: SLF001 - the one shared connection
    rows = db.execute(
        "SELECT id FROM HarnessRun WHERE status IN ('created', 'running')"
    ).fetchall()
    reconciled = 0
    for row in rows:
        run_id = row["id"]
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
        max_seq = db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM HarnessEvent WHERE runId = ?", (run_id,)
        ).fetchone()["s"]
        db.execute(
            "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id("evt"), run_id, event_type, max_seq + 1, now, error),
        )
        reconciled += 1
    if reconciled:
        db.commit()
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


def reconcile_orphaned_runs(store: Any, reason: str) -> dict[str, Any]:
    """Fail runs left by a dead process — but only when this process owns the
    runtime port. Returns a small report; never raises."""
    if not _runtime_port_is_free():
        return {"failed": 0, "skipped": "another runtime is already serving this port"}
    return {"failed": fail_orphaned_runs(store, reason)}


__all__ = ["fail_orphaned_runs", "reconcile_orphaned_runs"]
