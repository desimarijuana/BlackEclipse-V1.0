"""SLO tracking — objectives, error budgets and burn rate (C7 v2).

`SLORegistry` holds named objectives evaluated against a rolling window. Three
kinds are supported, because "success rate" alone cannot express latency,
resume time or orphan rates:

  * `ratio`      — good/total events, compliance = good/total (target = required
                   success ratio). Existing behavior, unchanged.
  * `percentile` — numeric observations, p95 must be `<= threshold`; `target` is
                   the required share of samples within the threshold.
  * `rate`       — failure ratio must be `<= threshold` (e.g. orphan rate = 0).

Each objective computes compliance, remaining error budget and a recent burn
rate. Violations are surfaced as `onSLOViolation` hook events by the hub.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

SLO_KINDS = ("ratio", "percentile", "rate")


def _percentile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    samples = sorted(values)
    idx = min(len(samples) - 1, max(0, int(q * (len(samples) - 1) + 0.5)))
    return samples[idx]


@dataclass
class SLO:
    name: str
    target: float
    description: str = ""
    good: int = 0
    total: int = 0
    window: int = 1000
    outcomes: deque[int] = field(default_factory=lambda: deque(maxlen=1000))
    kind: str = "ratio"
    threshold: Optional[float] = None
    unit: str = ""
    values: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_violation_at: Optional[float] = None
    violations: int = 0

    def record(self, *, good: bool) -> None:
        self.total += 1
        if good:
            self.good += 1
        self.outcomes.append(1 if good else 0)
        if not good:
            self.last_violation_at = time.time()

    def record_value(self, value: float) -> None:
        """Record one numeric observation (latency ms, seconds, USD, …)."""
        numeric = float(value)
        self.values.append(numeric)
        within = self.threshold is None or numeric <= float(self.threshold)
        self.record(good=within)

    def percentile(self, q: float) -> Optional[float]:
        return _percentile(list(self.values), q)

    # ── evaluation ───────────────────────────────────────────────────────────
    @property
    def _failure_ratio(self) -> Optional[float]:
        if self.total == 0:
            return None
        return (self.total - self.good) / self.total

    @property
    def error_budget(self) -> float:
        """The allowed failure ratio."""
        if self.kind == "rate":
            return max(0.0, float(self.threshold if self.threshold is not None else 0.0))
        if self.kind == "percentile":
            return max(0.0, 1.0 - self.target)
        return max(0.0, 1.0 - self.target)

    @property
    def compliance(self) -> Optional[float]:
        if self.total == 0:
            return None
        return self.good / self.total

    @property
    def budget_remaining(self) -> Optional[float]:
        if self.total == 0:
            return 1.0
        consumed = float(self._failure_ratio or 0.0)
        budget = self.error_budget
        if budget <= 0:
            return 0.0 if consumed > 0 else 1.0
        return max(0.0, 1.0 - consumed / budget)

    def evaluate(self) -> dict[str, Any]:
        compliance = self.compliance
        p50 = self.percentile(0.50)
        p95 = self.percentile(0.95)
        p99 = self.percentile(0.99)
        if self.kind == "percentile":
            healthy = p95 is None or self.threshold is None or p95 <= float(self.threshold)
        elif self.kind == "rate":
            allowed = float(self.threshold if self.threshold is not None else 0.0)
            healthy = (self._failure_ratio is None) or (self._failure_ratio <= allowed)
        else:
            healthy = compliance is None or compliance >= self.target
        if not healthy:
            self.violations += 1
        return {
            "name": self.name,
            "target": self.target,
            "kind": self.kind,
            "threshold": self.threshold,
            "unit": self.unit,
            "compliance": None if compliance is None else round(compliance, 5),
            "healthy": healthy,
            "total": self.total,
            "good": self.good,
            "p50": None if p50 is None else round(p50, 4),
            "p95": None if p95 is None else round(p95, 4),
            "p99": None if p99 is None else round(p99, 4),
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

    def define(
        self,
        name: str,
        target: float,
        *,
        description: str = "",
        window: int = 1000,
        kind: str = "ratio",
        threshold: Optional[float] = None,
        unit: str = "",
    ) -> SLO:
        """Define (or replace) an objective. Unknown kinds fall back to `ratio`."""
        resolved_kind = kind if kind in SLO_KINDS else "ratio"
        slo = SLO(
            name=name, target=max(0.0, min(1.0, target)), description=description,
            window=max(1, int(window)), kind=resolved_kind, threshold=threshold, unit=unit,
        )
        slo.outcomes = deque(maxlen=slo.window)
        slo.values = deque(maxlen=slo.window)
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

    def record_value(self, name: str, value: float) -> Optional[dict[str, Any]]:
        slo = self._slos.get(name)
        if slo is None:
            return None
        slo.record_value(value)
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


__all__ = ["SLO", "SLO_KINDS", "SLORegistry"]
