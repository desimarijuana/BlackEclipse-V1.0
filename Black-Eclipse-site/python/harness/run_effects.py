"""Durable effect ledger for at-most-once tool execution.

Checkpoint idempotency only knows about tool calls whose result was RECORDED. A
process can die after an external action succeeded but before that record — the
classic duplicate-execution window. This module closes it for effectful tools:

    begin(run, step, call)   -> state=started   (written BEFORE dispatch)
    finish(run, step, call)  -> state=done      (written after the result)

If a resume finds `started` with no `done`, the outcome is **unknown**. The run
must not call the tool again; it returns a typed refusal so the operator can
reconcile (broker terminal, git status, file hash). Read-only tools are not
tracked: retrying them is safe.

This is deliberately not an exactly-once claim. It is an at-most-once guard for
irreversible effects, with `unknown` as a first-class outcome.
"""

from __future__ import annotations

from typing import Any, Optional

from .persistence import now_iso
SCHEMA = """
CREATE TABLE IF NOT EXISTS RunEffect (
  runId       TEXT NOT NULL,
  stepIndex   INTEGER NOT NULL,
  toolCallId  TEXT NOT NULL,
  name        TEXT NOT NULL,
  effect      TEXT,
  state       TEXT NOT NULL,
  startedAt   TEXT NOT NULL,
  finishedAt  TEXT,
  ok          INTEGER,
  PRIMARY KEY (runId, stepIndex, toolCallId)
);
CREATE INDEX IF NOT EXISTS idx_run_effect_run ON RunEffect(runId);
"""


class RunEffects:
    """Effect lifecycle rows over the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        try:
            self._db.executescript(SCHEMA)
            self._db.commit()
        except Exception:  # noqa: BLE001 - the ledger must never break a run
            pass

    @property
    def _db(self):
        return self._store._db

    def state(self, run_id: str, step_index: int, tool_call_id: str) -> Optional[str]:
        try:
            row = self._db.execute(
                "SELECT state FROM RunEffect WHERE runId=? AND stepIndex=? AND toolCallId=?",
                (run_id, int(step_index), tool_call_id),
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        return str(row["state"]) if row else None

    def begin(self, run_id: str, step_index: int, tool_call_id: str,
              name: str, effect: Optional[str]) -> None:
        """Record intent BEFORE dispatch. A re-begin keeps the original row."""
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO RunEffect "
                "(runId, stepIndex, toolCallId, name, effect, state, startedAt) "
                "VALUES (?, ?, ?, ?, ?, 'started', ?)",
                (run_id, int(step_index), tool_call_id, name, effect, now_iso()),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - best effort; the run still executes
            pass

    def finish(self, run_id: str, step_index: int, tool_call_id: str, *,
               ok: bool) -> None:
        try:
            self._db.execute(
                "UPDATE RunEffect SET state='done', ok=?, finishedAt=? "
                "WHERE runId=? AND stepIndex=? AND toolCallId=?",
                (1 if ok else 0, now_iso(), run_id, int(step_index), tool_call_id),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass

    def has_started(self, run_id: str) -> bool:
        """True when any effect for this run is still unconfirmed."""
        try:
            row = self._db.execute(
                "SELECT 1 FROM RunEffect WHERE runId=? AND state='started' LIMIT 1",
                (run_id,),
            ).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            return True

    def has_unconfirmed(self, run_id: str) -> bool:
        """True when any effect is `started` OR its outcome became `unknown`.

        Recovery must treat both as unsafe: the external side effect may have
        happened, and re-running or skipping it silently would both be wrong.
        """
        try:
            row = self._db.execute(
                "SELECT 1 FROM RunEffect WHERE runId=? AND state IN ('started','unknown') LIMIT 1",
                (run_id,),
            ).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            return True

    def mark_unknown(self, run_id: str, step_index: int, tool_call_id: str) -> None:
        try:
            self._db.execute(
                "UPDATE RunEffect SET state='unknown', finishedAt=? "
                "WHERE runId=? AND stepIndex=? AND toolCallId=?",
                (now_iso(), run_id, int(step_index), tool_call_id),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["RunEffects", "SCHEMA"]
