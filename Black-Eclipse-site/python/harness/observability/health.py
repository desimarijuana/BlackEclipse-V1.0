"""Health registry — subsystem liveness/readiness for the health surface.

Each major Eclipse subsystem registers a checker returning `(state, detail)`.
The registry folds them into a single report with a deterministic worst-state
rollup. Observability ITSELF registers its exporters here, so a broken telemetry
backend shows as DEGRADED without ever being able to make the app UNHEALTHY by
itself (unless the operator explicitly asked for fail-closed).

States: HEALTHY > DEGRADED > UNKNOWN > UNHEALTHY (worst wins for rollup).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

HEALTHY, DEGRADED, UNKNOWN, UNHEALTHY = "HEALTHY", "DEGRADED", "UNKNOWN", "UNHEALTHY"
_RANK = {HEALTHY: 0, UNKNOWN: 1, DEGRADED: 2, UNHEALTHY: 3}

CheckResult = tuple[str, Optional[str]]
Checker = Callable[[], CheckResult]


@dataclass
class HealthReport:
    state: str
    checked_at: float
    subsystems: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "checkedAt": self.checked_at, "subsystems": self.subsystems}


class HealthRegistry:
    def __init__(self) -> None:
        self._checkers: dict[str, Checker] = {}
        self._kinds: dict[str, str] = {}

    def register(self, name: str, checker: Checker, *, kind: str = "subsystem") -> None:
        self._checkers[name] = checker
        self._kinds[name] = kind

    def unregister(self, name: str) -> None:
        self._checkers.pop(name, None)
        self._kinds.pop(name, None)

    def check(self, name: str) -> Optional[dict[str, Any]]:
        checker = self._checkers.get(name)
        if checker is None:
            return None
        return self._run(name, checker)

    def _run(self, name: str, checker: Checker) -> dict[str, Any]:
        started = time.monotonic()
        try:
            state, detail = checker()
            if state not in _RANK:
                state, detail = UNKNOWN, f"invalid state {state!r}"
        except Exception as exc:  # noqa: BLE001 - a broken checker is UNHEALTHY, not a crash
            state, detail = UNHEALTHY, f"checker raised {type(exc).__name__}: {exc}"
        return {
            "name": name,
            "kind": self._kinds.get(name, "subsystem"),
            "state": state,
            "detail": detail,
            "latencyMs": round((time.monotonic() - started) * 1000.0, 2),
        }

    def report(self, *, only: Optional[list[str]] = None) -> HealthReport:
        names = only if only is not None else list(self._checkers.keys())
        subsystems: dict[str, dict[str, Any]] = {}
        worst = HEALTHY
        for name in names:
            checker = self._checkers.get(name)
            if checker is None:
                continue
            result = self._run(name, checker)
            subsystems[name] = result
            if _RANK[result["state"]] > _RANK[worst]:
                worst = result["state"]
        return HealthReport(state=worst, checked_at=time.time(), subsystems=subsystems)


__all__ = [
    "HealthRegistry",
    "HEALTHY",
    "DEGRADED",
    "UNKNOWN",
    "UNHEALTHY",
]
