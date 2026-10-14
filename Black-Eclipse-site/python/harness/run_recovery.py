"""Recovery helpers for runs orphaned by a process restart.

The runtime executes agent runs in-process, so a run row left `created`/`running`
by a previous process can never finish: no task will ever complete it and a
client streaming it would wait forever. `fail_orphaned_runs` marks each one
failed with a durable `run.failed` event so every consumer sees a terminal state.

Lives in its own module (rather than on `AgentMemoryStore`) so `persistence.py`
stays within its size ratchet; it uses the store's ONE shared connection, exactly
like the other per-subsystem stores under `harness/`.
"""

from __future__ import annotations

import json
from typing import Any

from .persistence import new_id, now_iso


def fail_orphaned_runs(store: Any, reason: str) -> int:
    """Fail non-terminal runs left behind by a previous process. Returns the count.

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
        error = json.dumps({"code": "RUN_ORPHANED", "message": reason})
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
