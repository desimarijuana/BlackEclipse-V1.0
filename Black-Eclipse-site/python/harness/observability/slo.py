"""SLO tracking — objectives, error budgets and burn rate.

An `SLORegistry` holds named objectives evaluated against a rolling window of
outcomes. Each `SLO` accumulates `good`/`total` counts; the registry computes
compliance, the remaining error budget and a simple burn rate (recent violation
velocity relative to the budget). Violations are surfaced as `onSLOViolation`
hook events by the hub.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SLO:
    name: str
    target: float
    description: str = ""
    good: int = 0
    total: int = 0
    window: int = 1000
    outcomes: deque[int] = field(default_factory=lambda: deque(maxlen=1000))
    last_violation_at: Optional[float] = None
    violations: int = 0

    def record(self, *, good: bool) -> None:
        self.total += 1
        if good:
            self.good += 1
        self.outcomes.append(1 if good else 0)
        if not good:
            self.last_violation_at = time.time()

    @property
    def compliance(self) -> Optional[float]:
        if self.total == 0:
            return None
        return self.good / self.total

    @property
    def error_budget(self) -> float:
        """The allowed failure ratio (1 - target)."""
        return max(0.0, 1.0 - self.target)

    @property
    def budget_remaining(self) -> Optional[float]:
        if self.total == 0:
            return 1.0
        consumed = (self.total - self.good) / self.total
        budget = self.error_budget
        if budget <= 0:
            return 0.0 if consumed > 0 else 1.0
        return max(0.0, 1.0 - consumed / budget)

    def evaluate(self) -> dict[str, Any]:
        compliance = self.compliance
        healthy = compliance is None or compliance >= self.target
        if not healthy:
            self.violations += 1
        return {
            "name": self.name,
            "target": self.target,
            "compliance": None if compliance is None else round(compliance, 5),
            "healthy": healthy,
            "total": self.total,
            "good": self.good,
            "errorBudgetRemaining": None if self.budget_remaining is None else round(self.budget_remaining, 5),
            "burnRate": self._burn_rate(),
            "violations": self.violations,
            "lastViolationAt": self.last_violation_at,
            "description": self.description,
        }

    def _burn_rate(self, recent: int = 100) -> Optional[float]:
        if self.total == 0 or self.error_budget <= 0:
            return None
        window = list(self.outcomes)[-recent:]
        if not window:
            return None
        failures = sum(1 for x in window if x == 0)
        observed_ratio = failures / len(window)
        return round(observed_ratio / self.error_budget, 4)


class SLORegistry:
    def __init__(self) -> None:
        self._slos: dict[str, SLO] = {}

    def define(self, name: str, target: float, *, description: str = "", window: int = 1000) -> SLO:
        slo = SLO(name=name, target=max(0.0, min(1.0, target)), description=description, window=window)
        slo.outcomes = deque(maxlen=window)
        self._slos[name] = slo
        return slo

    def get(self, name: str) -> Optional[SLO]:
        return self._slos.get(name)

    def record(self, name: str, *, good: bool) -> Optional[dict[str, Any]]:
        slo = self._slos.get(name)
        if slo is None:
            return None
        slo.record(good=good)
        return slo.evaluate()

    def report(self) -> dict[str, Any]:
        evaluations = [slo.evaluate() for slo in self._slos.values()]
        violating = [e for e in evaluations if not e["healthy"]]
        return {
            "objectives": evaluations,
            "violations": violating,
            "allHealthy": not violating,
        }

    def snapshot(self) -> dict[str, Any]:
        return {name: slo.evaluate() for name, slo in self._slos.items()}


__all__ = ["SLO", "SLORegistry"]
