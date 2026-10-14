"""Stall watchdog for agent runs — every run reaches a terminal state.

Belt-and-suspenders beside the per-call hard deadlines (`async_timeout.py`): a
run row in `created`/`running` whose last recorded activity is older than its
own model budget + grace is FAILED with code `RUN_STALLED`, a durable
`run.failed` event is appended, the live SSE stream is closed and the active
task is cancelled. A client can therefore never wait forever, whatever strand
of the runtime misbehaves (a swallowed cancellation, a provider that stops
emitting after its deadline, a bug in a new subsystem).

Runs legitimately waiting on a USER DECISION (last event `approval.requested` /
`user.approval.required`) are exempt: their wait is bounded by the approval
timeout inside the run itself, not by model progress.

Pure `find_stalled` for tests + `sweep_stalled_runs` as the DB adapter.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import time
from typing import Any, Callable, Optional

from .agents import AGENT_PRESETS
from .persistence import new_id, now_iso

log = logging.getLogger("harness.watchdog")

DEFAULT_MODEL_BUDGET_S = 120.0
STALL_GRACE_S = 60.0
SWEEP_INTERVAL_S = 30.0
APPROVAL_EVENTS = frozenset({"approval.requested", "user.approval.required"})

_STALLED_SQL = """
SELECT r.id, r.status, r.agentId,
       COALESCE(r.startedAt, r.createdAt) AS started,
       (SELECT MAX(e.at) FROM HarnessEvent e WHERE e.runId = r.id) AS lastEventAt,
       (SELECT e2.type FROM HarnessEvent e2 WHERE e2.runId = r.id ORDER BY e2.seq DESC LIMIT 1) AS lastEventType
FROM HarnessRun r
WHERE r.status IN ('created', 'running')
"""


def stall_threshold_s(agent_id: Optional[str]) -> float:
    """The silence budget for one run: its own model-call budget + grace.

    `runTimeoutMs` bounds ONE model call; a healthy run can be silent for at
    most that long (longer silences mean the deadline machinery itself failed).
    The per-agent value matters: Eclipse Agent declares 120s, Code Agent 600s.
    """
    preset = AGENT_PRESETS.get(agent_id or "")
    budget_ms = getattr(preset, "runTimeoutMs", None) or int(DEFAULT_MODEL_BUDGET_S * 1000)
    return budget_ms / 1000.0 + STALL_GRACE_S


def _epoch(stamp: Optional[str]) -> Optional[float]:
    if not stamp:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def find_stalled(
    rows: list[dict[str, Any]],
    now_epoch: float,
    threshold_for: Callable[[Optional[str]], float] = stall_threshold_s,
) -> list[str]:
    """The pure detector: run ids whose last activity exceeds their silence budget."""
    stalled: list[str] = []
    for row in rows:
        if row.get("lastEventType") in APPROVAL_EVENTS:
            continue  # waiting on the user; bounded by the approval timeout
        last = _epoch(row.get("lastEventAt")) or _epoch(row.get("started"))
        if last is None:
            continue
        if now_epoch - last > threshold_for(row.get("agentId")):
            stalled.append(str(row["id"]))
    return stalled


def sweep_stalled_runs(service: Any, now_epoch: Optional[float] = None) -> list[str]:
    """Fail every currently stalled run; returns the run ids. Never raises."""
    try:
        db = service.store._db  # noqa: SLF001 - the one shared connection
        rows = [dict(r) for r in db.execute(_STALLED_SQL).fetchall()]
        stalled = find_stalled(rows, now_epoch if now_epoch is not None else time.time())
    except Exception:  # noqa: BLE001 - the watch must never break the runtime
        log.warning("run watchdog sweep failed", exc_info=True)
        return []
    for run_id in stalled:
        try:
            now = now_iso()
            error = json.dumps({
                "code": "RUN_STALLED",
                "message": "no progress within this run's model budget; marked failed so the stream closes",
            })
            cur = db.execute(
                "UPDATE HarnessRun SET status = 'failed', error = ?, updatedAt = ?, finishedAt = ? "
                "WHERE id = ? AND status IN ('created', 'running')",
                (error, now, now, run_id),
            )
            if not cur.rowcount:
                continue  # finished between the scan and the update
            max_seq = db.execute(
                "SELECT COALESCE(MAX(seq), 0) AS s FROM HarnessEvent WHERE runId = ?", (run_id,)
            ).fetchone()["s"]
            db.execute(
                "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, 'run.failed', ?, ?, ?)",
                (new_id("evt"), run_id, max_seq + 1, now, error),
            )
            db.commit()
            service.bus.end_stream(run_id)
            service.cancel(run_id)  # cooperative; the hard deadlines do the rest
            log.warning("watchdog failed stalled run %s", run_id)
        except Exception:  # noqa: BLE001 - one bad row must not stop the sweep
            log.warning("watchdog failed to fail run %s", run_id, exc_info=True)
    return stalled


_watchdog_task: Optional["asyncio.Task[None]"] = None


async def start_run_watchdog(service: Any, interval_s: float = SWEEP_INTERVAL_S) -> None:
    """Start the periodic sweep (idempotent). Best-effort; never blocks boot."""
    global _watchdog_task
    if _watchdog_task is not None and not _watchdog_task.done():
        return

    async def _loop() -> None:
        while True:
            # Runs ON the event loop: `service.bus.end_stream` / `service.cancel`
            # touch asyncio primitives, which must stay on this thread. The query
            # itself is short (non-terminal runs only).
            sweep_stalled_runs(service)
            await asyncio.sleep(interval_s)

    _watchdog_task = asyncio.create_task(_loop())


async def stop_run_watchdog() -> None:
    """Stop the sweep (idempotent, never raises)."""
    global _watchdog_task
    task = _watchdog_task
    _watchdog_task = None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


__all__ = [
    "APPROVAL_EVENTS",
    "STALL_GRACE_S",
    "SWEEP_INTERVAL_S",
    "find_stalled",
    "stall_threshold_s",
    "start_run_watchdog",
    "stop_run_watchdog",
    "sweep_stalled_runs",
]
