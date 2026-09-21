"""Parallel retrieval with error isolation (Milestone 2H).

Independent retrievals run concurrently under:
  * a concurrency limit,
  * an individual timeout per task,
  * partial-failure handling (one failure never destroys the others),
  * cancellation,
  * error isolation,
  * optional per-task event reporting.

No distributed infrastructure — asyncio is sufficient for a single-process
runtime.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .sources import SourceOutcome

DEFAULT_CONCURRENCY = 6
DEFAULT_TIMEOUT_S = 20.0


@dataclass
class TaskResult:
    name: str
    outcome: Optional[SourceOutcome] = None
    error: Optional[str] = None
    timed_out: bool = False
    cancelled: bool = False
    latencyMs: int = 0

    @property
    def ok(self) -> bool:
        return self.outcome is not None and self.outcome.status == "OK"


async def run_parallel(
    tasks: list[tuple[str, Callable[[], Awaitable[SourceOutcome]]]],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    on_start: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[TaskResult], None]] = None,
) -> list[TaskResult]:
    """Run independent retrieval tasks concurrently. Order of results is stable."""
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: dict[str, TaskResult] = {}

    async def _run(name: str, fn: Callable[[], Awaitable[SourceOutcome]]) -> None:
        started = time.monotonic()
        if on_start:
            on_start(name)
        async with semaphore:
            try:
                outcome = await asyncio.wait_for(fn(), timeout=timeout_s)
                result = TaskResult(
                    name=name,
                    outcome=outcome,
                    latencyMs=int((time.monotonic() - started) * 1000),
                )
            except asyncio.TimeoutError:
                result = TaskResult(
                    name=name, error=f"{name} timed out after {timeout_s}s",
                    timed_out=True, latencyMs=int((time.monotonic() - started) * 1000),
                )
            except asyncio.CancelledError:
                result = TaskResult(
                    name=name, error=f"{name} was cancelled", cancelled=True,
                    latencyMs=int((time.monotonic() - started) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - isolate every failure
                result = TaskResult(
                    name=name, error=str(exc), latencyMs=int((time.monotonic() - started) * 1000),
                )
        results[name] = result
        if on_done:
            on_done(result)

    await asyncio.gather(*(_run(name, fn) for name, fn in tasks))
    return [results[name] for name, _ in tasks if name in results]


__all__ = ["run_parallel", "TaskResult", "DEFAULT_CONCURRENCY", "DEFAULT_TIMEOUT_S"]
