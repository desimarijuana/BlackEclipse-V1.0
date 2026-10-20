"""Deterministic utility and acceptance rules for the RSL hill climb.

Utility is a transparent ranking signal, never a claim of truth. Critical
regressions are a veto, not a term that a good score can outweigh. An
unmeasured candidate is rejected: a missing value is not zero and not progress.

The weights are data so a reviewer can read exactly why a state was preferred.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from ..evaluation.regression import DEFAULT_GATES, detect_regressions
from ..evaluation.stats import wilson_interval

UNMEASURED = "UNMEASURED"
MAX_RATIO = 5.0


@dataclass(frozen=True)
class UtilityWeights:
    """Bounded weights for the hill climb's ranking signal."""

    success: float = 1.0
    target: float = 0.5
    cost: float = 0.10
    latency: float = 0.10
    coverage: float = 0.0
    targetDimension: str = "task_success"
    minImprovement: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _aggregates(metrics: Any) -> dict[str, Any]:
    if isinstance(metrics, Mapping):
        value = metrics.get("aggregates")
        if isinstance(value, Mapping):
            return dict(value)
        return dict(metrics)
    value = getattr(metrics, "aggregates", None)
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _measured(metrics: Any) -> int:
    value = None
    if isinstance(metrics, Mapping):
        value = metrics.get("measuredTrials", metrics.get("measured"))
    else:
        value = getattr(metrics, "measuredTrials", None)
        if value is None:
            measured_trials = getattr(metrics, "measured_trials", None)
            value = measured_trials() if callable(measured_trials) else measured_trials
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _success_signal(metrics: Any, aggregates: Mapping[str, Any]) -> tuple[Optional[float], str]:
    """The success component: Wilson lower bound when counts exist, else the rate."""
    successes = _number(aggregates.get("successes"))
    sample = _number(aggregates.get("sampleSize") or aggregates.get("trials"))
    if successes is not None and sample is not None and sample > 0:
        low, _ = wilson_interval(int(successes), int(sample))
        if low is not None:
            return low, "wilson"
    value = _number(aggregates.get("task_success"))
    return (value, "rate") if value is not None else (None, UNMEASURED)


def utility(
    metrics: Any,
    *,
    weights: Optional[UtilityWeights] = None,
    baseline: Any = None,
) -> dict[str, Any]:
    """Score one measured state; return the total plus every component.

    `baseline` is only used to normalize cost and latency so their weights do
    not depend on the absolute unit of the metric.
    """
    settings = weights or UtilityWeights()
    aggregates = _aggregates(metrics)
    base_aggregates = _aggregates(baseline)
    measured = _measured(metrics)

    success, successSource = _success_signal(metrics, aggregates)
    components: dict[str, Optional[float]] = {
        "success": success,
        "target": None,
        "cost": None,
        "latency": None,
        "coverage": _number(aggregates.get("coverage")),
    }

    target_dimension = str(settings.targetDimension or "task_success")
    if target_dimension != "task_success":
        components["target"] = _number(aggregates.get(target_dimension))

    for key in ("cost", "latency"):
        value = _number(aggregates.get(key))
        if value is None:
            continue
        base_value = _number(base_aggregates.get(key))
        if base_value is not None and base_value > 0:
            components[key] = min(MAX_RATIO, value / base_value)
        else:
            components[key] = min(MAX_RATIO, value)

    reasons: list[str] = []
    if measured <= 0:
        reasons.append("no measured trials")
    if success is None:
        reasons.append("task_success is UNMEASURED")

    total = 0.0
    if components["success"] is not None:
        total += settings.success * float(components["success"])
    if components["target"] is not None:
        total += settings.target * float(components["target"])
    if components["cost"] is not None:
        total -= settings.cost * float(components["cost"])
    if components["latency"] is not None:
        total -= settings.latency * float(components["latency"])
    if components["coverage"] is not None:
        total += settings.coverage * float(components["coverage"])

    return {
        "utility": round(total, 6),
        "weights": settings.to_dict(),
        "components": components,
        "successSource": successSource,
        "measuredTrials": measured,
        "unmeasured": measured <= 0 or success is None,
        "reasons": reasons,
    }


def acceptance(
    current_metrics: Any,
    candidate_metrics: Any,
    *,
    weights: Optional[UtilityWeights] = None,
    gates: Optional[tuple] = None,
) -> dict[str, Any]:
    """Decide whether a candidate may replace the current state.

    Rejection is ordered: unmeasured first, then a critical regression, then a
    utility that does not improve. A warning never vetoes; a critical regression
    always does.
    """
    settings = weights or UtilityWeights()
    current = utility(current_metrics, weights=settings)
    candidate = utility(candidate_metrics, weights=settings, baseline=current_metrics)
    regressions = detect_regressions(
        {"aggregates": _aggregates(current_metrics)},
        {"aggregates": _aggregates(candidate_metrics)},
        gates or DEFAULT_GATES,
    )

    reasons: list[str] = []
    if candidate["measuredTrials"] <= 0:
        reasons.append("candidate has no measured trials")
    if candidate["components"]["success"] is None:
        reasons.append("candidate task_success is UNMEASURED")

    critical = [
        item for item in regressions["regressions"]
        if any(
            gate.dimension == item.get("dimension") and gate.critical
            for gate in (gates or DEFAULT_GATES)
        )
    ]
    if critical:
        reasons.append("critical regression: " + ", ".join(
            str(item.get("dimension")) for item in critical
        ))

    improvement = float(candidate["utility"]) - float(current["utility"])
    if not reasons and improvement <= settings.minImprovement:
        reasons.append(
            f"utility did not improve ({current['utility']} → {candidate['utility']})"
        )

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "current": current,
        "candidate": candidate,
        "improvement": round(improvement, 6),
        "regressions": regressions["regressions"],
        "warnings": regressions["warnings"],
    }


__all__ = [
    "MAX_RATIO",
    "UNMEASURED",
    "UtilityWeights",
    "acceptance",
    "utility",
]
