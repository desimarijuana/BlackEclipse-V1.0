"""Bounded graph-health watch.

The Health surface is useful only if someone looks at it. This task reads the
SAME bounded telemetry on a cadence, persists its verdict, and publishes
`graph.health_degraded` / `graph.health_recovered` only on a TRANSITION. It never
touches a run, never creates one, and never changes a workflow.

Disabled with `HARNESS_GRAPH_HEALTH_SECONDS=0`. Thin data is `insufficient`, not
`healthy`: the failure-rate and queue-wait gates need a minimum run count.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any, Optional

from ..event_system.emit import publish_event

log = logging.getLogger("harness.graph_runtime.health_watch")

DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_WINDOW_HOURS = 1
DEFAULT_MIN_RUNS = 5
DEFAULT_FAILURE_RATE = 0.5
DEFAULT_QUEUE_P95_MS = 60_000.0


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def evaluate_health(
    health: dict[str, Any],
    *,
    min_runs: int = DEFAULT_MIN_RUNS,
    failure_rate: float = DEFAULT_FAILURE_RATE,
    queue_p95_ms: float = DEFAULT_QUEUE_P95_MS,
) -> dict[str, Any]:
    """Classify one health payload; reasons are explicit, never inferred."""
    runs = health.get("runs") or {}
    total = int(runs.get("total") or 0)
    if total < max(1, int(min_runs)):
        return {
            "status": "insufficient",
            "reasons": [f"only {total} run(s) in the window; need {max(1, int(min_runs))}"],
        }
    reasons: list[str] = []
    rate = runs.get("failureRate")
    if isinstance(rate, (int, float)) and rate > failure_rate:
        reasons.append(f"failure rate {rate:.1%} > {failure_rate:.1%}")
    queue = health.get("queueWaitMs") or {}
    p95 = queue.get("p95")
    if isinstance(p95, (int, float)) and p95 > queue_p95_ms:
        reasons.append(f"queue wait p95 {p95:.0f} ms > {queue_p95_ms:.0f} ms")
    return {"status": "degraded" if reasons else "healthy", "reasons": reasons}


class GraphHealthWatcher:
    """One background task; publishes only status transitions."""

    def __init__(self, service: Any = None, *, interval_seconds: Optional[int] = None) -> None:
        self.service = service
        self.interval_seconds = (
            _env_int("HARNESS_GRAPH_HEALTH_SECONDS", DEFAULT_INTERVAL_SECONDS)
            if interval_seconds is None
            else max(0, int(interval_seconds))
        )
        self.window_hours = max(1, min(_env_int("HARNESS_GRAPH_HEALTH_WINDOW_HOURS", DEFAULT_WINDOW_HOURS), 168))
        self.min_runs = max(1, _env_int("HARNESS_GRAPH_HEALTH_MIN_RUNS", DEFAULT_MIN_RUNS))
        self.failure_rate = _env_float("HARNESS_GRAPH_HEALTH_FAILURE_RATE", DEFAULT_FAILURE_RATE)
        self.queue_p95_ms = _env_float("HARNESS_GRAPH_HEALTH_QUEUE_MS", DEFAULT_QUEUE_P95_MS)
        self._task: Optional[asyncio.Task[Any]] = None
        self._stopping = False

    async def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="graph-health-watch")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(
                    self.interval_seconds + random.uniform(0, self.interval_seconds * 0.1)
                )
            except asyncio.CancelledError:
                return
            if self._stopping:
                return
            try:
                await asyncio.to_thread(self.check)
            except Exception:  # noqa: BLE001 - one check never kills the watch
                log.warning("graph health watch check failed", exc_info=True)

    def check(self) -> dict[str, Any]:
        """Read telemetry once and publish a transition (degraded/recovered)."""
        store = getattr(getattr(self.service, "graphs", None), "_store", None)
        if store is None:
            return {"status": "unmeasured", "previous": None, "transition": None, "reasons": []}
        health = store.health(window_hours=self.window_hours)
        verdict = evaluate_health(
            health,
            min_runs=self.min_runs,
            failure_rate=self.failure_rate,
            queue_p95_ms=self.queue_p95_ms,
        )
        status = str(verdict["status"])
        reasons = list(verdict.get("reasons") or [])
        previous = str((store.watch_state() or {}).get("status") or "unmeasured")
        transition = None
        if status != previous and status in ("degraded", "healthy"):
            transition = status
        store.save_watch_state(status, reasons)
        if transition:
            try:
                store.save_alert(status, reasons)
            except Exception:  # noqa: BLE001 - history is best-effort
                pass

        if transition == "degraded":
            publish_event("graph.health_degraded", {
                "windowHours": self.window_hours,
                "status": status,
                "reasons": reasons,
                "failureRate": (health.get("runs") or {}).get("failureRate"),
                "queueP95Ms": (health.get("queueWaitMs") or {}).get("p95"),
                "runs": (health.get("runs") or {}).get("total"),
            })
        elif transition == "healthy":
            publish_event("graph.health_recovered", {
                "windowHours": self.window_hours,
                "status": status,
                "runs": (health.get("runs") or {}).get("total"),
            })
        return {
            "status": status,
            "previous": previous,
            "transition": transition,
            "reasons": reasons,
            "checkedAt": (store.watch_state() or {}).get("checkedAt"),
        }


__all__ = [
    "DEFAULT_FAILURE_RATE",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_MIN_RUNS",
    "DEFAULT_QUEUE_P95_MS",
    "GraphHealthWatcher",
    "evaluate_health",
]
