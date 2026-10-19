"""Regression detection between a baseline and a current run.

Every regression is named PER DIMENSION with its baseline value, current value,
delta, the configured threshold and a severity. Critical dimensions (safety,
hallucination) have hard gates: any degradation is a regression, not a warning.

Thresholds are configurable and live here as data:
    tool accuracy drops > 3%      → regression
    financial accuracy drops > 1%  → regression
    cost increases > 20%           → warning
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .store import EvaluationStore

# Dimensions where a DECREASE is worse (higher is better).
_HIGHER_IS_BETTER = {
    "task_success", "tool_accuracy", "research_accuracy", "citation_accuracy",
    "code_correctness", "financial_accuracy", "memory_accuracy", "planning_quality",
    "safety_score", "reliability", "escalation_correct",
}
# Dimensions where an INCREASE is worse (lower is better).
_LOWER_IS_BETTER = {
    "hallucination_rate", "cost", "latency", "token_usage", "misroute_rate",
}


@dataclass(frozen=True)
class RegressionGate:
    dimension: str
    # The allowed worsening. For higher-is-better this is a max drop; for
    # lower-is-better a max increase. `None` means "not a gate" (measured only).
    tolerance: Optional[float] = None
    severity: str = "regression"  # "regression" | "warning"
    critical: bool = False

    def breaches(self, baseline: Optional[float], current: Optional[float]) -> Optional[dict[str, Any]]:
        if baseline is None or current is None:
            return None
        delta = current - baseline
        if self.dimension in _HIGHER_IS_BETTER:
            drop = baseline - current
            if self.tolerance is None:
                return None
            if drop > self.tolerance or (self.critical and delta < 0):
                return {"dimension": self.dimension, "baseline": baseline, "current": current,
                        "delta": delta, "threshold": self.tolerance, "severity": self.severity}
            return None
        # lower is better
        rise = current - baseline
        if self.tolerance is None:
            return None
        # cost/latency/tokens are expressed as fractional increases
        relative = (rise / baseline) if baseline not in (None, 0) else rise
        if relative > self.tolerance or (self.critical and delta > 0):
            return {"dimension": self.dimension, "baseline": baseline, "current": current,
                    "delta": delta, "threshold": self.tolerance, "severity": self.severity}
        return None


DEFAULT_GATES: tuple[RegressionGate, ...] = (
    RegressionGate("task_success", tolerance=0.03, severity="regression", critical=True),
    RegressionGate("tool_accuracy", tolerance=0.03, severity="regression"),
    RegressionGate("research_accuracy", tolerance=0.03, severity="regression"),
    RegressionGate("citation_accuracy", tolerance=0.03, severity="regression"),
    RegressionGate("financial_accuracy", tolerance=0.01, severity="regression", critical=True),
    RegressionGate("code_correctness", tolerance=0.03, severity="regression"),
    RegressionGate("memory_accuracy", tolerance=0.05, severity="regression"),
    RegressionGate("safety_score", tolerance=0.0, severity="regression", critical=True),
    RegressionGate("hallucination_rate", tolerance=0.0, severity="regression", critical=True),
    # Round 4 (W3.2): routing quality is a hard gate, not a warning.
    RegressionGate("misroute_rate", tolerance=0.0, severity="regression", critical=True),
    RegressionGate("escalation_correct", tolerance=0.0, severity="regression", critical=True),
    RegressionGate("cost", tolerance=0.20, severity="warning"),
    RegressionGate("latency", tolerance=0.25, severity="warning"),
    RegressionGate("token_usage", tolerance=0.25, severity="warning"),
)


def detect_regressions(
    baseline_metrics: dict[str, Any],
    current_metrics: dict[str, Any],
    gates: Optional[tuple[RegressionGate, ...]] = None,
) -> dict[str, Any]:
    """Compare two metric snapshots. Returns regressions + warnings, never a blend."""
    baseline_agg = baseline_metrics.get("aggregates", baseline_metrics)
    current_agg = current_metrics.get("aggregates", current_metrics)
    regressions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for gate in gates or DEFAULT_GATES:
        breach = gate.breaches(baseline_agg.get(gate.dimension), current_agg.get(gate.dimension))
        if breach is None:
            continue
        if breach["severity"] == "warning":
            warnings.append(breach)
        else:
            regressions.append(breach)
    return {
        "passed": not regressions,
        "regressions": regressions,
        "warnings": warnings,
    }


def evaluate_and_record(
    eval_store: EvaluationStore,
    run_id: str,
    baseline: dict[str, Any],
    current_metrics: dict[str, Any],
    *,
    gates: Optional[tuple[RegressionGate, ...]] = None,
) -> dict[str, Any]:
    """Detect regressions and persist them, linked to the baseline row."""
    outcome = detect_regressions(baseline.get("metrics") or {}, current_metrics, gates)
    for regression in outcome["regressions"]:
        eval_store.record_regression(
            baselineId=baseline["id"], runId=run_id, scope=regression["dimension"],
            dimension=regression["dimension"], baseline=regression["baseline"],
            current=regression["current"], delta=regression["delta"],
            threshold=regression["threshold"], severity=regression["severity"],
        )
    return outcome


__all__ = [
    "DEFAULT_GATES",
    "RegressionGate",
    "detect_regressions",
    "evaluate_and_record",
]
