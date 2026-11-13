"""Run lineage, durable checkpoints and idempotent resume (Phase 1).

Before this, a run had no identity that survived a crash and no parent that
recorded where it came from. This module owns the three additive facts that fix
that, all in `agent-memory.db` (the runtime's own database), never JDdS:

  * `HarnessRun.parentRunId` / `workflowId` — the run that spawned this one (a
    skill invocation, a workflow step) and the workflow it belongs to.
  * `RunCheckpoint` — one bounded row per durable boundary (agent step completed,
    tool result completed, terminal status). The payload is a REFERENCE (step
    index, pending tool calls, accumulated usage, resolved allowlist) — never a
    second copy of the event log.
  * `ToolExecutionIdempotency` — one row per executed `(runId, stepIndex,
    toolCallId)`, recording the outcome so a resume REUSES the recorded result
    instead of re-executing a side-effecting call.

Ownership mirrors `mcp/approvals.py`: the module is bound to the single
`AgentMemoryStore` sqlite connection and owns only its own tables + columns. That
keeps `persistence.py` from growing past its size ratchet while keeping ONE
database and ONE connection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from .checkpoint_io import restore_messages, serialize_run_messages
from .migrations import Migration, MigrationRunner
from .persistence import now_iso

log = logging.getLogger("harness.run_lineage")


def _notify(event_type: str, data: dict[str, Any], *, run_id: str = "") -> None:
    """W8 telemetry for a durable boundary. Fail-open; never affects the write."""
    try:
        from .observability.bridge import publish  # noqa: PLC0415

        publish(event_type, data, run_id=run_id)
    except Exception:  # noqa: BLE001 - telemetry must not fail a checkpoint
        pass


class CheckpointWriteFailed(RuntimeError):
    """A durable boundary could not be written.

    A run must not continue past a failed boundary: the next resume would
    otherwise start from a checkpoint that does not match the conversation. The
    caller maps this to `CHECKPOINT_WRITE_FAILED` and stops the run honestly.
    """

    code = "CHECKPOINT_WRITE_FAILED"

# The durable message cursor. A checkpoint stores the conversation's sequence
# number; the messages themselves live here once, untruncated, so a long run
# resumes with its early evidence intact.
LINEAGE_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id="2026-11-11-001-run-message-cursor",
        description="RunMessage: the full durable conversation behind a checkpoint cursor",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS RunMessage (
              id        TEXT PRIMARY KEY,
              runId     TEXT NOT NULL,
              seq       INTEGER NOT NULL,
              payload   TEXT NOT NULL,
              createdAt TEXT NOT NULL,
              FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_run_message_run ON RunMessage(runId, seq)",
        ),
    ),
)

# A checkpoint payload is a bounded reference, not a trace. These caps keep a
# pathological run from turning the checkpoint table into a second event log.
MAX_CHECKPOINT_TOOL_CALLS = 50
MAX_CHECKPOINT_ALLOWLIST = 200


def idempotency_key(run_id: str, step_index: int, tool_call_id: str) -> str:
    """Stable digest of (runId, stepIndex, toolCallId) — the resume-safety key."""
    raw = f"{run_id}|{int(step_index)}|{tool_call_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bound_checkpoint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim a checkpoint payload to a bounded reference.

    The payload must be enough to resume — step index, message reference, pending
    tool calls, accumulated usage, resolved allowlist — and nothing more. Pending
    tool calls and the allowlist are capped so a runaway run cannot bloat the
    checkpoint table.
    """
    out = dict(payload or {})
    pending = out.get("pendingToolCalls")
    if isinstance(pending, list):
        out["pendingToolCalls"] = pending[:MAX_CHECKPOINT_TOOL_CALLS]
    allow = out.get("allowlist")
    if isinstance(allow, list):
        out["allowlist"] = allow[:MAX_CHECKPOINT_ALLOWLIST]
    return out


def _checkpoint_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "runId": row["runId"],
        "seq": row["seq"],
        "kind": row["kind"],
        "payload": json.loads(row["payload"]) if row["payload"] else {},
        "createdAt": row["createdAt"],
    }


class RunLineage:
    """Lineage + checkpoints + idempotency over the ONE agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        """Idempotent DDL: lineage columns + checkpoint/idempotency tables.

        `CREATE TABLE IF NOT EXISTS` never alters an existing table, so the two
        additive `HarnessRun` columns are added explicitly when absent. On a
        downgrade the extra tables/columns are simply ignored by older code.
        """
        existing = {row["name"] for row in self._db.execute("PRAGMA table_info(HarnessRun)").fetchall()}
        for name in ("parentRunId", "workflowId"):
            if name not in existing:
                self._db.execute(f"ALTER TABLE HarnessRun ADD COLUMN {name} TEXT")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS RunCheckpoint (
              id        TEXT PRIMARY KEY,
              runId     TEXT NOT NULL,
              seq       INTEGER NOT NULL,
              kind      TEXT NOT NULL,
              payload   TEXT,
              createdAt TEXT NOT NULL,
              FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_checkpoint_run ON RunCheckpoint(runId, seq)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS ToolExecutionIdempotency (
              key         TEXT PRIMARY KEY,
              runId       TEXT NOT NULL,
              toolCallId  TEXT NOT NULL,
              name        TEXT NOT NULL,
              ok          INTEGER NOT NULL,
              text        TEXT NOT NULL,
              error       TEXT,
              createdAt   TEXT NOT NULL,
              FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_idem_run ON ToolExecutionIdempotency(runId)"
        )
        # W6: pre-dispatch idempotency. `state` is additive; an existing row was
        # written after a completed call, so it is `done` by definition.
        idem_columns = {
            row["name"] for row in self._db.execute(
                "PRAGMA table_info(ToolExecutionIdempotency)"
            ).fetchall()
        }
        for name, decl in (
            ("state", "TEXT NOT NULL DEFAULT 'done'"),
            ("startedAt", "TEXT"),
            ("finishedAt", "TEXT"),
        ):
            if name not in idem_columns:
                self._db.execute(
                    f"ALTER TABLE ToolExecutionIdempotency ADD COLUMN {name} {decl}"
                )
        self._db.commit()
        MigrationRunner(self._db, "agent-memory").apply(LINEAGE_MIGRATIONS)

    # ── Lineage ─────────────────────────────────────────────────────────────
    def set_run_parent(
        self, run_id: str, parent_run_id: Optional[str], workflow_id: Optional[str] = None,
    ) -> None:
        sets = ["parentRunId = ?", "updatedAt = ?"]
        params: list[Any] = [parent_run_id, now_iso()]
        if workflow_id is not None:
            sets.insert(1, "workflowId = ?")
            params.insert(1, workflow_id)
        params.append(run_id)
        self._db.execute(f"UPDATE HarnessRun SET {', '.join(sets)} WHERE id = ?", params)
        self._db.commit()

    def list_child_runs(self, parent_run_id: str, limit: int = 100) -> list[str]:
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            "SELECT id FROM HarnessRun WHERE parentRunId=? ORDER BY createdAt ASC LIMIT ?",
            (parent_run_id, limit),
        ).fetchall()
        return [r["id"] for r in rows]

    def lineage(self, run_id: str, *, max_depth: int = 10, max_children: int = 100) -> dict[str, Any]:
        """The parent chain (bounded) plus the direct children of a run.

        A cycle (which the schema cannot prevent if a caller is misconfigured) is
        broken by tracking visited ids — the walk never loops.
        """
        parents: list[dict[str, Any]] = []
        visited = {run_id}
        current = run_id
        for _ in range(max(0, int(max_depth))):
            row = self._db.execute(
                "SELECT id, parentRunId, status FROM HarnessRun WHERE id=?", (current,)
            ).fetchone()
            if row is None or not row["parentRunId"]:
                break
            parent_id = row["parentRunId"]
            if parent_id in visited:
                break
            visited.add(parent_id)
            prow = self._db.execute(
                "SELECT id, parentRunId, status FROM HarnessRun WHERE id=?", (parent_id,)
            ).fetchone()
            if prow is None:
                parents.append({"id": parent_id, "status": None, "missing": True})
                break
            parents.append({"id": prow["id"], "status": prow["status"], "missing": False})
            current = parent_id
        children = self.list_child_runs(run_id, limit=max_children)
        return {"runId": run_id, "parents": parents, "children": children}

    # ── Checkpoints ─────────────────────────────────────────────────────────
    def _next_checkpoint_seq_locked(self, run_id: str) -> int:
        seq_row = self._db.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM RunCheckpoint WHERE runId=?", (run_id,)
        ).fetchone()
        return int(seq_row["m"]) + 1

    def _insert_checkpoint_locked(
        self, run_id: str, kind: str, payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        seq = self._next_checkpoint_seq_locked(run_id)
        checkpoint = {
            "id": f"ckpt_{run_id}_{seq}",
            "runId": run_id,
            "seq": seq,
            "kind": kind,
            "payload": bound_checkpoint_payload(payload or {}),
            "createdAt": now_iso(),
        }
        self._db.execute(
            "INSERT INTO RunCheckpoint (id, runId, seq, kind, payload, createdAt) VALUES (?, ?, ?, ?, ?, ?)",
            (checkpoint["id"], run_id, seq, kind,
             json.dumps(checkpoint["payload"]), checkpoint["createdAt"]),
        )
        return checkpoint

    def _write_messages_locked(self, run_id: str, serialized: list[dict[str, Any]]) -> Optional[int]:
        """Write the full RunMessage cursor inside the caller's transaction."""
        if not serialized:
            return None
        for seq, payload in enumerate(serialized):
            self._db.execute(
                "INSERT OR REPLACE INTO RunMessage (id, runId, seq, payload, createdAt) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"msg_{run_id}_{seq}", run_id, seq, json.dumps(payload), now_iso()),
            )
        self._db.execute(
            "DELETE FROM RunMessage WHERE runId=? AND seq >= ?",
            (run_id, len(serialized)),
        )
        return len(serialized) - 1

    def save_checkpoint(
        self, run_id: str, kind: str, payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record a durable checkpoint at a boundary (ordered per run)."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            checkpoint = self._insert_checkpoint_locked(run_id, kind, payload)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return checkpoint

    def save_boundary(
        self,
        run_id: str,
        kind: str,
        payload: Optional[dict[str, Any]] = None,
        messages: Optional[list[Any]] = None,
        *,
        retries: int = 1,
    ) -> dict[str, Any]:
        """Commit the message cursor and the checkpoint in ONE transaction.

        A crash between the two legacy writes used to leave a checkpoint with a
        stale tail (or a message cursor with no boundary). This method makes the
        pair atomic: either both are visible or neither is.

        Serialization happens BEFORE `BEGIN IMMEDIATE` so the SQLite write lock
        covers only the inserts. A transient `busy` failure is retried once; a
        persistent failure raises `CheckpointWriteFailed`.
        """
        serialized: list[dict[str, Any]] = []
        if messages:
            serialized = serialize_run_messages(list(messages))
        last_error: Optional[Exception] = None
        started = time.monotonic()
        for attempt in range(max(0, int(retries)) + 1):
            try:
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    cursor = self._write_messages_locked(run_id, serialized)
                    merged = dict(payload or {})
                    if cursor is not None:
                        merged["messageSeq"] = cursor
                    checkpoint = self._insert_checkpoint_locked(run_id, kind, merged)
                    self._db.execute("COMMIT")
                    _notify("checkpoint.write", {
                        "ok": True, "kind": kind,
                        "durationMs": int((time.monotonic() - started) * 1000.0),
                    }, run_id=run_id)
                    return checkpoint
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
            except Exception as exc:  # noqa: BLE001 - retried, then surfaced honestly
                last_error = exc
                if attempt >= retries:
                    break
        _notify("checkpoint.write", {
            "ok": False, "kind": kind,
            "durationMs": int((time.monotonic() - started) * 1000.0),
        }, run_id=run_id)
        raise CheckpointWriteFailed(
            f"could not write the {kind!r} boundary for {run_id!r}: {last_error}"
        ) from last_error

    def latest_checkpoint(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM RunCheckpoint WHERE runId=? ORDER BY seq DESC LIMIT 1", (run_id,)
        ).fetchone()
        return _checkpoint_row(row) if row else None

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM RunCheckpoint WHERE runId=? ORDER BY seq ASC", (run_id,)
        ).fetchall()
        return [_checkpoint_row(r) for r in rows]

    # ── Durable message cursor ───────────────────────────────────────────────
    def save_messages(self, run_id: str, messages: list[Any]) -> Optional[int]:
        """Persist the run's full conversation; return the last sequence index.

        Idempotent: a checkpoint can be written at the same boundary twice. Rows
        beyond the current tail are deleted, so a shorter rewrite cannot leave a
        stale message behind. Returns None when there is nothing to persist.
        """
        try:
            serialized = serialize_run_messages(list(messages or []))
        except Exception:  # noqa: BLE001 - a cursor must never break a run
            log.warning("failed to serialize run messages", exc_info=True)
            return None
        if not serialized:
            return None
        self._db.execute("BEGIN IMMEDIATE")
        try:
            last = self._write_messages_locked(run_id, serialized)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return last

    def load_messages(self, run_id: str) -> list[Any]:
        """Load the durable conversation in order; [] when the cursor is absent."""
        rows = self._db.execute(
            "SELECT payload FROM RunMessage WHERE runId=? ORDER BY seq ASC", (run_id,)
        ).fetchall()
        serialized: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                serialized.append(payload)
        return restore_messages(serialized)

    def message_cursor(self, run_id: str) -> Optional[int]:
        row = self._db.execute(
            "SELECT MAX(seq) AS m FROM RunMessage WHERE runId=?", (run_id,)
        ).fetchone()
        return None if row is None or row["m"] is None else int(row["m"])

    # ── Idempotency ─────────────────────────────────────────────────────────
    def mark_tool_started(
        self, run_id: str, step_index: int, tool_call_id: str, name: str,
    ) -> None:
        """Record intent BEFORE dispatch.

        A crash after this row and before the result leaves `state='started'`.
        An effectful tool is then treated as `unknown` on resume and is never
        executed a second time. `INSERT OR IGNORE` means a re-entry can never
        downgrade an existing `done` row.
        """
        key = idempotency_key(run_id, step_index, tool_call_id)
        try:
            self._db.execute(
                """INSERT OR IGNORE INTO ToolExecutionIdempotency
                   (key, runId, toolCallId, name, ok, text, error, createdAt,
                    state, startedAt)
                   VALUES (?, ?, ?, ?, 0, '', NULL, ?, 'started', ?)""",
                (key, run_id, tool_call_id, name, now_iso(), now_iso()),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - the ledger must never break dispatch
            log.warning("failed to record tool start", exc_info=True)

    def mark_tool_done(
        self, run_id: str, step_index: int, tool_call_id: str, result: Any,
    ) -> None:
        """Record the terminal result of a call (replaces `mark_tool_executed`)."""
        key = idempotency_key(run_id, step_index, tool_call_id)
        error = getattr(result, "error", None)
        try:
            self._db.execute(
                """INSERT INTO ToolExecutionIdempotency
                   (key, runId, toolCallId, name, ok, text, error, createdAt,
                    state, startedAt, finishedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     name=excluded.name, ok=excluded.ok, text=excluded.text,
                     error=excluded.error, state='done',
                     finishedAt=excluded.finishedAt""",
                (
                    key, run_id, tool_call_id, getattr(result, "name", ""),
                    1 if getattr(result, "ok", False) else 0,
                    str(getattr(result, "text", ""))[:8000],
                    error.model_dump_json() if error is not None else None,
                    now_iso(), now_iso(), now_iso(),
                ),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - idempotency is a safety net, not a gate
            log.warning("failed to record tool result", exc_info=True)

    # Backwards-compatible alias: existing callers recorded after execution.
    def mark_tool_executed(
        self, run_id: str, step_index: int, tool_call_id: str, result: Any,
    ) -> None:
        self.mark_tool_done(run_id, step_index, tool_call_id, result)

    def mark_tool_unknown(
        self, run_id: str, step_index: int, tool_call_id: str,
    ) -> None:
        """The call started but its outcome was never recorded."""
        key = idempotency_key(run_id, step_index, tool_call_id)
        try:
            self._db.execute(
                "UPDATE ToolExecutionIdempotency SET state='unknown', finishedAt=? "
                "WHERE key=? AND state <> 'done'",
                (now_iso(), key),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            log.warning("failed to record unknown tool state", exc_info=True)

    def was_tool_executed(
        self, run_id: str, step_index: int, tool_call_id: str,
    ) -> Optional[dict[str, Any]]:
        """The recorded outcome of an already-started call, or None."""
        key = idempotency_key(run_id, step_index, tool_call_id)
        row = self._db.execute(
            "SELECT * FROM ToolExecutionIdempotency WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        keys = set(row.keys())
        return {
            "key": row["key"],
            "runId": row["runId"],
            "toolCallId": row["toolCallId"],
            "name": row["name"],
            "ok": bool(row["ok"]),
            "text": row["text"],
            "error": json.loads(row["error"]) if row["error"] else None,
            "createdAt": row["createdAt"],
            "state": str(row["state"]) if "state" in keys and row["state"] else "done",
            "startedAt": row["startedAt"] if "startedAt" in keys else None,
            "finishedAt": row["finishedAt"] if "finishedAt" in keys else None,
        }


__all__ = [
    "CheckpointWriteFailed",
    "RunLineage",
    "idempotency_key",
    "bound_checkpoint_payload",
]
