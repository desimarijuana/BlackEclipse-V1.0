"""In-process background runner for heavy quant runs.

A large backtest, optimization, walk-forward or Monte-Carlo sweep must not block
the request loop. `QuantRunner` executes a coroutine factory as an asyncio task
behind a concurrency semaphore, tracks status/progress, and supports
cancellation. It adds no new infrastructure (no queue, no worker process): the
FastAPI event loop already runs the work; this just moves it off the request and
makes it observable.

A run's result is retained in memory for `ttl_seconds` (the durable copy is the
experiment artifact written by the store when the run completes).
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
class RunState:
    id: str
    kind: str
    message: str = ""
    status: str = "queued"            # queued | running | completed | failed | cancelled
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
            "runId": self.id, "kind": self.kind, "status": self.status,
            "stage": self.stage, "done": self.done, "total": self.total, "percent": percent,
            "message": self.message,
            "createdAt": self.created_at, "startedAt": self.started_at,
            "finishedAt": self.finished_at, "error": self.error,
        }
        if include_result and self.status == "completed":
            out["result"] = self.result
        return out


class QuantRunner:
    def __init__(self, *, max_concurrent: int = 2, ttl_seconds: float = 3600.0,
                 history: int = 200) -> None:
        self._runs: dict[str, RunState] = {}
        self._order: list[str] = []
        self._sem = asyncio.Semaphore(max(1, max_concurrent))
        self._ttl = ttl_seconds
        self._history = history

    def submit(self, kind: str, factory: Factory, *, message: str = "") -> str:
        run_id = f"qrun_{uuid.uuid4().hex[:16]}"
        state = RunState(id=run_id, kind=kind, message=message)
        self._runs[run_id] = state
        self._order.append(run_id)
        self._prune()
        state.task = asyncio.get_running_loop().create_task(self._execute(run_id, factory))
        return run_id

    async def _execute(self, run_id: str, factory: Factory) -> None:
        state = self._runs[run_id]
        async with self._sem:
            state.status = "running"
            state.started_at = state.started_at or _now()
            try:
                result = await factory(state.set_progress)
                state.result = result
                state.status = "completed"
            except asyncio.CancelledError:
                state.status = "cancelled"
                raise
            except Exception as exc:  # noqa: BLE001 - a failed run is data
                state.status = "failed"
                state.error = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                state.finished_at = _now()

    def get(self, run_id: str, *, include_result: bool = False) -> Optional[dict]:
        state = self._runs.get(run_id)
        return state.public(include_result=include_result) if state else None

    def result(self, run_id: str) -> Optional[dict]:
        state = self._runs.get(run_id)
        if state is None:
            return None
        return state.result if state.status == "completed" else None

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
        return True

    def _prune(self) -> None:
        now = time.time()
        # Keep the history bounded.
        while len(self._order) > self._history:
            old = self._order.pop(0)
            self._runs.pop(old, None)
        # Drop terminal runs older than the TTL.
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


_runner: Optional[QuantRunner] = None


def get_runner() -> QuantRunner:
    global _runner
    if _runner is None:
        _runner = QuantRunner()
    return _runner


def reset_runner() -> None:
    """Tests only."""
    global _runner
    _runner = None


__all__ = ["QuantRunner", "RunState", "get_runner", "reset_runner"]
