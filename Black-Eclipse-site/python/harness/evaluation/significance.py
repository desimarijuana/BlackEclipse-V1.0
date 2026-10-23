"""Paired significance tests for two measured arms.

A candidate is measured on the SAME tasks as the state it would replace, so the
comparison is paired: resample TASKS, not trials. A Wilson interval on one arm
answers "how precise is this arm"; a paired bootstrap answers the question the
loop actually asks: "is the DIFFERENCE bigger than noise?"

The helpers are pure and seeded. They never decide a change by themselves:
`utility.acceptance` decides, and only when the operator enables the
significance requirement.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Optional, Sequence

DEFAULT_BOOTSTRAP = 10_000
DEFAULT_SEED = 0
DEFAULT_ALPHA = 0.05


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def paired_rates(metrics: Any) -> dict[str, float]:
    """Extract per-task rates from a metrics dict (absent -> empty).

    Accepted shapes:
    - `{"taskRates": {task_id: 0..1}}`
    - `{"task_rates": {...}}`
    - `{"perTask": {task_id: {"rate": 0..1, ...}}}`
    - `{"tasks": {task_id: {"rate": ...}}}`
    - `{"taskPassed": {task_id: true|false}}`
    """
    if not isinstance(metrics, Mapping):
        # A SuiteResult carries TaskResult rows with measured trials. Derive the
        # per-task rate here so the caller does not have to project it first.
        task_rows = getattr(metrics, "tasks", None)
        if task_rows is None:
            return {}
        rates: dict[str, float] = {}
        for task_result in task_rows or ():
            task = getattr(task_result, "task", None)
            task_id = (
                getattr(task, "id", None)
                or getattr(task_result, "task_id", None)
            )
            trials = [
                trial for trial in (getattr(task_result, "trials", None) or ())
                if not getattr(trial, "unmeasured", False)
            ]
            if task_id and trials:
                rates[str(task_id)] = sum(
                    1 for trial in trials if getattr(trial, "passed", False)
                ) / len(trials)
        return rates
    raw = (
        metrics.get("taskRates")
        or metrics.get("task_rates")
        or metrics.get("perTask")
        or metrics.get("tasks")
        or metrics.get("taskPassed")
        or metrics.get("task_passed")
    )
    if not isinstance(raw, Mapping):
        return {}
    rates: dict[str, float] = {}
    for task_id, value in raw.items():
        if isinstance(value, Mapping):
            value = value.get("rate", value.get("passed"))
        number = _number(value)
        if number is not None:
            rates[str(task_id)] = max(0.0, min(1.0, number))
    return rates


def _percentile(ordered: Sequence[float], q: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower]) * (1.0 - weight) + float(ordered[upper]) * weight


def paired_bootstrap(
    base_rates: Mapping[str, float],
    candidate_rates: Mapping[str, float],
    *,
    n: int = DEFAULT_BOOTSTRAP,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Bootstrap the mean paired difference by resampling tasks.

    Returns the observed delta, a percentile CI, a one-sided bootstrap p-value
    (`P(delta <= 0)`) and the paired-task count. Fewer than two paired tasks is
    not evidence: the CI is `None` and `insufficient` is true.
    """
    paired = sorted(set(base_rates) & set(candidate_rates))
    deltas = [
        float(candidate_rates[task]) - float(base_rates[task])
        for task in paired
    ]
    if len(deltas) < 2:
        return {
            "pairedTasks": len(deltas),
            "delta": round(sum(deltas) / len(deltas), 6) if deltas else None,
            "ciLow": None,
            "ciHigh": None,
            "pValue": None,
            "bootstrapped": 0,
            "alpha": float(alpha),
            "insufficient": True,
        }
    observed = sum(deltas) / len(deltas)
    draws = max(100, min(int(n), 200_000))
    generator = random.Random(int(seed))
    count = len(deltas)
    means: list[float] = []
    for _ in range(draws):
        total = 0.0
        for _ in range(count):
            total += deltas[generator.randrange(count)]
        means.append(total / count)
    means.sort()
    low = _percentile(means, alpha / 2.0)
    high = _percentile(means, 1.0 - alpha / 2.0)
    at_or_below_zero = sum(1 for value in means if value <= 0.0)
    p_value = at_or_below_zero / draws
    return {
        "pairedTasks": count,
        "delta": round(observed, 6),
        "ciLow": round(low, 6),
        "ciHigh": round(high, 6),
        "pValue": round(p_value, 6),
        "bootstrapped": draws,
        "alpha": float(alpha),
        "insufficient": False,
    }


def mcnemar(
    base_passed: Mapping[str, bool],
    candidate_passed: Mapping[str, bool],
) -> dict[str, Any]:
    """Exact McNemar for paired pass/fail tasks (normal approx above 200)."""
    paired = sorted(set(base_passed) & set(candidate_passed))
    b = sum(
        1 for task in paired
        if not bool(base_passed[task]) and bool(candidate_passed[task])
    )
    c = sum(
        1 for task in paired
        if bool(base_passed[task]) and not bool(candidate_passed[task])
    )
    total = b + c
    if total == 0:
        p_value = 1.0
    elif total <= 200:
        tail = sum(math.comb(total, i) for i in range(min(b, c) + 1))
        p_value = min(1.0, 2.0 * tail / (2 ** total))
    else:
        chi2 = (abs(b - c) - 1) ** 2 / total
        p_value = math.erfc(math.sqrt(max(0.0, chi2) / 2.0))
    return {
        "pairedTasks": len(paired),
        "baseOnlyPass": c,
        "candidateOnlyPass": b,
        "discordant": total,
        "pValue": round(min(1.0, max(0.0, p_value)), 6),
        "method": "exact" if total <= 200 else "normal",
    }


def required_trials(
    effect: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = 0.8,
) -> Optional[int]:
    """A coarse two-proportion sample estimate for a target absolute effect.

    This is a planning aid, not a guarantee: it assumes a balanced 50/50 base
    rate and independent trials. The loop prints it so an operator can see when
    a corpus is too small to support the claim.
    """
    size = abs(float(effect or 0.0))
    if size <= 0:
        return None
    z_alpha = 1.959963984540054 if abs(alpha - 0.05) < 1e-9 else 1.96
    z_power = 0.8416212335729143 if abs(power - 0.8) < 1e-9 else 0.84
    n = ((z_alpha + z_power) ** 2) * 2.0 * 0.25 / (size ** 2)
    return max(2, int(math.ceil(n)))


__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_BOOTSTRAP",
    "DEFAULT_SEED",
    "mcnemar",
    "paired_bootstrap",
    "paired_rates",
    "required_trials",
]
