"""Trial statistics: pass rates, pass@k, variance, confidence, flakiness.

Agent execution is stochastic, so one successful run is not proof a capability
works. These are the deterministic estimators the trial system reports, with a
small-sample caveat baked in (a single trial yields a wide interval and the
report says so).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

STABLE_PASS = "stable_pass"
STABLE_FAILURE = "stable_failure"
FLAKY = "flaky"
UNMEASURED = "unmeasured"


def mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def variance(values: Sequence[float], *, ddof: int = 1) -> Optional[float]:
    if len(values) <= ddof:
        return 0.0 if values else None
    mu = sum(values) / len(values)
    return sum((v - mu) ** 2 for v in values) / (len(values) - ddof)


def stdev(values: Sequence[float]) -> Optional[float]:
    var = variance(values)
    return math.sqrt(var) if var is not None else None


def _comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k)


def pass_at_k(n: int, c: int, k: int) -> Optional[float]:
    """Unbiased pass@k estimator (Codex/HumanEval): 1 - C(n-c, k)/C(n, k).

    ``n`` trials, ``c`` passing. Returned for ``k <= n`` only; beyond the sample
    size the estimate is not defined and returns ``None`` (never a fabricated 1).
    """
    if n <= 0:
        return None
    k = max(1, min(k, n))
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - _comb(n - c, k) / _comb(n, k)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[Optional[float], Optional[float]]:
    """Wilson score interval for a binomial proportion (robust at small n)."""
    if n <= 0:
        return None, None
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def classify_flakiness(outcomes: Sequence[bool]) -> str:
    if not outcomes:
        return UNMEASURED
    if all(outcomes):
        return STABLE_PASS
    if not any(outcomes):
        return STABLE_FAILURE
    return FLAKY


@dataclass
class TrialStats:
    n: int
    successes: int
    pass_rate: float
    pass_at_1: float
    pass_at_k: Optional[float]
    k: int
    variance: Optional[float]
    std_dev: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    flakiness: str
    outcomes: list[bool] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "successes": self.successes,
            "passRate": round(self.pass_rate, 4),
            "passAt1": round(self.pass_at_1, 4),
            "passAtK": None if self.pass_at_k is None else round(self.pass_at_k, 4),
            "k": self.k,
            "variance": None if self.variance is None else round(self.variance, 6),
            "stdDev": None if self.std_dev is None else round(self.std_dev, 6),
            "ciLow": None if self.ci_low is None else round(self.ci_low, 4),
            "ciHigh": None if self.ci_high is None else round(self.ci_high, 4),
            "flakiness": self.flakiness,
            "meanScore": None if not self.scores else round(sum(self.scores) / len(self.scores), 4),
            "scoreStdDev": None if not self.scores else round(stdev(self.scores) or 0.0, 4),
        }


def aggregate_trials(outcomes: Sequence[bool], *, scores: Optional[Sequence[float]] = None,
                     k: int = 1) -> TrialStats:
    outcomes = list(outcomes)
    n = len(outcomes)
    c = sum(1 for o in outcomes if o)
    low, high = wilson_interval(c, n)
    return TrialStats(
        n=n,
        successes=c,
        pass_rate=(c / n) if n else 0.0,
        pass_at_1=(c / n) if n else 0.0,
        pass_at_k=pass_at_k(n, c, k),
        k=k,
        variance=variance([1.0 if o else 0.0 for o in outcomes]),
        std_dev=stdev([1.0 if o else 0.0 for o in outcomes]),
        ci_low=low,
        ci_high=high,
        flakiness=classify_flakiness(outcomes),
        outcomes=outcomes,
        scores=list(scores or []),
    )


__all__ = [
    "FLAKY",
    "STABLE_FAILURE",
    "STABLE_PASS",
    "UNMEASURED",
    "TrialStats",
    "aggregate_trials",
    "classify_flakiness",
    "mean",
    "median",
    "pass_at_k",
    "stdev",
    "variance",
    "wilson_interval",
]
