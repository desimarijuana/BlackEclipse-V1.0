"""In-process background runner for heavy statistical jobs.

A large multi-asset IC sweep or feature-matrix build must not block the request
loop. `StatsRunner` executes a coroutine factory as an asyncio task behind a
concurrency semaphore, tracks status/progress, supports cancellation, and mirrors
terminal state into the durable `StatsRun` table. No new infrastructure: the
FastAPI event loop already runs the work.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

ProgressFn = Callable[[str, int, int], None]
Factory = Callable[[ProgressFn], Awaitable[dict]]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


@dataclass
class StatsRunState:
    id: str
    kind: str
    message: str = ""
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    stage: str = ""
    done: int = 0
    total: int = 0
    result: Optional[dict] = None
    error: Optional[dict] = None
    task: Optional[asyncio.Task] = None

    def set_progress(self, stage: str, done: int, total: int) -> None:
        self.stage = stage
        self.done = int(done)
        self.total = int(total)

    def public(self, *, include_result: bool = False) -> dict[str, Any]:
        percent = round(100.0 * self.done / self.total, 1) if self.total else 0.0
        out: dict[str, Any] = {
            "runId": self.id, "kind": self.kind, "status": self.status, "stage": self.stage,
            "done": self.done, "total": self.total, "percent": percent, "message": self.message,
            "createdAt": self.created_at, "startedAt": self.started_at,
            "finishedAt": self.finished_at, "error": self.error,
        }
        if include_result and self.status == "completed":
            out["result"] = self.result
        return out


class StatsRunner:
    def __init__(self, *, max_concurrent: int = 2, ttl_seconds: float = 3600.0,
                 history: int = 200, store: Any = None) -> None:
        self._runs: dict[str, StatsRunState] = {}
        self._order: list[str] = []
        self._sem = asyncio.Semaphore(max(1, max_concurrent))
        self._ttl = ttl_seconds
        self._history = history
        self._store = store

    def set_store(self, store: Any) -> None:
        self._store = store

    def submit(self, kind: str, factory: Factory, *, message: str = "") -> str:
        run_id = f"srun_{uuid.uuid4().hex[:16]}"
        state = StatsRunState(id=run_id, kind=kind, message=message)
        self._runs[run_id] = state
        self._order.append(run_id)
        self._prune()
        self._persist(state)
        state.task = asyncio.get_running_loop().create_task(self._execute(run_id, factory))
        return run_id

    async def _execute(self, run_id: str, factory: Factory) -> None:
        state = self._runs[run_id]
        async with self._sem:
            state.status = "running"
            state.started_at = state.started_at or _now()
            self._persist(state)
            try:
                state.result = await factory(state.set_progress)
                state.status = "completed"
            except asyncio.CancelledError:
                state.status = "cancelled"
                raise
            except Exception as exc:  # noqa: BLE001 - a failed run is data
                state.status = "failed"
                state.error = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                state.finished_at = _now()
                self._persist(state)

    def _persist(self, state: StatsRunState) -> None:
        if self._store is None:
            return
        try:
            self._store.upsert_run(
                state.id, kind=state.kind, status=state.status, stage=state.stage,
                done=state.done, total=state.total, message=state.message,
                error=state.error, finished_at=state.finished_at,
            )
        except Exception:  # noqa: BLE001 - persistence must never break a run
            pass

    def get(self, run_id: str, *, include_result: bool = False) -> Optional[dict]:
        state = self._runs.get(run_id)
        return state.public(include_result=include_result) if state else None

    def result(self, run_id: str) -> Optional[dict]:
        state = self._runs.get(run_id)
        return state.result if state and state.status == "completed" else None

    def list(self) -> list[dict]:
        return [self._runs[r].public() for r in reversed(self._order) if r in self._runs]

    def cancel(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if state is None or state.status not in ("queued", "running"):
            return False
        if state.task is not None:
            state.task.cancel()
        state.status = "cancelled"
        state.finished_at = _now()
        self._persist(state)
        return True

    def _prune(self) -> None:
        now = time.time()
        while len(self._order) > self._history:
            old = self._order.pop(0)
            self._runs.pop(old, None)
        for run_id in list(self._runs):
            state = self._runs[run_id]
            if state.status in ("completed", "failed", "cancelled") and state.finished_at:
                try:
                    finished = time.mktime(time.strptime(state.finished_at, "%Y-%m-%dT%H:%M:%SZ"))
                except ValueError:
                    continue
                if now - finished > self._ttl:
                    self._runs.pop(run_id, None)
                    if run_id in self._order:
                        self._order.remove(run_id)


_runner: Optional[StatsRunner] = None


def get_runner() -> StatsRunner:
    global _runner
    if _runner is None:
        _runner = StatsRunner()
    return _runner


def reset_runner() -> None:
    """Tests only."""
    global _runner
    _runner = None


__all__ = ["StatsRunner", "StatsRunState", "get_runner", "reset_runner"]
