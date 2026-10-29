"""Bounded, unattended advisory-outcome scoring.

This is the cadence the Advisory Ledger was missing: on an interval, score the
recommendations whose stated horizon has elapsed and whose entry price was
recorded. It is observational only — it records how a past recommendation turned
out; it does not create recommendations and it does not touch any approval gate.

Safe degradation:

* no advisory service → no-op;
* nothing due → no market request at all;
* no market gateway → a named result, never a guessed mark;
* no entry price / not due → counted, never scored;
* a kill switch (`HARNESS_ADVISORY_AUTO_EVALUATE=0`) stops all ticks.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from ..persistence import now_iso

log = logging.getLogger("harness.advisory.cadence")


def _env_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _env_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AdvisoryCadenceConfig:
    enabled: bool = True
    interval_seconds: int = 900
    max_per_tick: int = 50
    benchmark_return: Optional[float] = None

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "AdvisoryCadenceConfig":
        env = os.environ if environ is None else environ
        benchmark: Optional[float] = None
        raw_benchmark = env.get("HARNESS_ADVISORY_BENCHMARK_RETURN")
        if raw_benchmark not in (None, ""):
            try:
                benchmark = float(raw_benchmark)
            except (TypeError, ValueError):
                benchmark = None
        return cls(
            enabled=_env_bool(env.get("HARNESS_ADVISORY_AUTO_EVALUATE"), True),
            interval_seconds=_env_int(
                env.get("HARNESS_ADVISORY_EVAL_INTERVAL_SECONDS"), 900, 60, 86400,
            ),
            max_per_tick=_env_int(
                env.get("HARNESS_ADVISORY_EVAL_MAX"), 50, 1, 500,
            ),
            benchmark_return=benchmark,
        )


async def run_once(
    service: Any,
    config: AdvisoryCadenceConfig,
    *,
    now: Optional[str] = None,
) -> dict[str, Any]:
    """Score the due, priced recommendations once. Never invents a mark."""
    if not config.enabled:
        return {"checked": 0, "evaluated": 0, "reason": "disabled"}
    advisory = getattr(service, "advisory", None)
    if advisory is None:
        return {"checked": 0, "evaluated": 0, "reason": "advisory_unavailable"}
    try:
        due = advisory.due_decisions(
            now=now or now_iso(), limit=config.max_per_tick,
        )
    except Exception as exc:  # noqa: BLE001 - a cadence reports, never crashes boot
        return {"checked": 0, "evaluated": 0, "reason": "due_lookup_failed", "error": str(exc)}
    if not due:
        return {"checked": 0, "evaluated": 0, "reason": "nothing_due"}

    gateway = None
    getter = getattr(service, "server_market_gateway", None)
    if callable(getter):
        try:
            gateway = getter()
        except Exception:  # noqa: BLE001
            gateway = None
    if gateway is None:
        gateway = getattr(service, "market_gateway", None)
    if gateway is None:
        return {
            "checked": len(due), "evaluated": 0,
            "reason": "no_market_gateway", "dueIds": [d["id"] for d in due],
        }

    try:
        result = await advisory.auto_evaluate(
            gateway,
            benchmark_return=config.benchmark_return,
            limit=config.max_per_tick,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 - one tick must never kill the loop
        return {"checked": len(due), "evaluated": 0, "reason": "evaluate_failed", "error": str(exc)}
    return {
        "checked": len(due),
        "evaluated": int(result.get("evaluated") or 0),
        "skippedNoPrice": int(result.get("skippedNoPrice") or 0),
        "skippedNotDue": int(result.get("skippedNotDue") or 0),
        "outcomeIds": [o.get("decisionId") for o in result.get("outcomes") or []],
        "reason": "evaluated" if result.get("evaluated") else "no_marks",
    }


class AdvisoryCadence:
    """One bounded background task, started/stopped by the runtime lifespan."""

    def __init__(
        self,
        service: Any,
        config: Optional[AdvisoryCadenceConfig] = None,
    ) -> None:
        self.service = service
        self.config = config or AdvisoryCadenceConfig.from_env()
        self._task: Optional[asyncio.Task[Any]] = None
        self._lock = asyncio.Lock()
        self._last_result: dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._last_run_at: Optional[str] = None

    async def start(self) -> None:
        if not self.config.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="advisory-cadence")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def run_now(self, *, now: Optional[str] = None) -> dict[str, Any]:
        if self._lock.locked():
            return {"checked": 0, "evaluated": 0, "reason": "busy"}
        async with self._lock:
            self._last_run_at = now or now_iso()
            try:
                self._last_result = await run_once(
                    self.service, self.config, now=now,
                )
                self._last_error = self._last_result.get("error")
            except Exception as exc:  # noqa: BLE001 - the loop must survive
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._last_result = {
                    "checked": 0, "evaluated": 0,
                    "reason": "unexpected_error", "error": self._last_error,
                }
            return dict(self._last_result)

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_now()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - run_now already records
                log.warning("advisory cadence tick failed", exc_info=True)
            await asyncio.sleep(max(60, int(self.config.interval_seconds)))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.enabled),
            "intervalSeconds": int(self.config.interval_seconds),
            "maxPerTick": int(self.config.max_per_tick),
            "benchmarkReturn": self.config.benchmark_return,
            "running": bool(self._task is not None and not self._task.done()),
            "lastRunAt": self._last_run_at,
            "lastResult": dict(self._last_result),
            "lastError": self._last_error,
        }


__all__ = [
    "AdvisoryCadence",
    "AdvisoryCadenceConfig",
    "run_once",
]
