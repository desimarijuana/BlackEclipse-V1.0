"""Recovery helpers for runs orphaned by a process restart.

The runtime executes agent runs in-process, so a run row left `created`/`running`
by a previous process can never finish: no task will ever complete it and a
client streaming it would wait forever. `fail_orphaned_runs` marks each one
failed with a durable `run.failed` event so every consumer sees a terminal state.
A run whose last event was an APPROVAL WAIT (it was paused on an operator's
decision, not on model progress) is reported as `RUN_INTERRUPTED` rather than a
generic orphan: the wait was lost and nothing was applied.

Lives in its own module (rather than on `AgentMemoryStore`) so `persistence.py`
stays within its size ratchet; it uses the store's ONE shared connection, exactly
like the other per-subsystem stores under `harness/`.
"""

from __future__ import annotations

import json
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


def fail_orphaned_runs(store: Any, reason: str) -> int:
    """Fail non-terminal runs left behind by a previous process. Returns the count.

    A run paused on an operator approval (its last event is an approval wait) is
    reported as `RUN_INTERRUPTED` with a message that says nothing was applied;
    every other non-terminal run is `RUN_ORPHANED` with `reason`.

    Idempotent (a second pass finds nothing) and safe to call on every boot.
    """
    db = store._db  # noqa: SLF001 - the one shared connection
    rows = db.execute(
        "SELECT id FROM HarnessRun WHERE status IN ('created', 'running')"
    ).fetchall()
    failed = 0
    for row in rows:
        run_id = row["id"]
        now = now_iso()
        if _last_event_type(db, run_id) in APPROVAL_WAIT_EVENTS:
            code, message = INTERRUPTED_CODE, INTERRUPTED_MESSAGE
        else:
            code, message = "RUN_ORPHANED", reason
        error = json.dumps({"code": code, "message": message})
        db.execute(
            "UPDATE HarnessRun SET status = 'failed', error = ?, updatedAt = ?, finishedAt = ? WHERE id = ?",
            (error, now, now, run_id),
        )
        max_seq = db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM HarnessEvent WHERE runId = ?", (run_id,)
        ).fetchone()["s"]
        db.execute(
            "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, 'run.failed', ?, ?, ?)",
            (new_id("evt"), run_id, max_seq + 1, now, error),
        )
        failed += 1
    if failed:
        db.commit()
    return failed


__all__ = ["fail_orphaned_runs"]
