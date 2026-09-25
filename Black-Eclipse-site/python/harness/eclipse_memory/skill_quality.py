"""Skill usefulness metrics — derived from real execution records.

The brief requires learning/skill quality to be measured, not asserted. This
module computes operator-visible metrics for one skill version from the
`SkillExecution` rows it already produces (no new instrumentation, no model, no
fabrication):

  * execution success / failure rate;
  * output-validation rate (the schema-validation outcome);
  * tool-budget failure rate (a `TOOL_BUDGET_EXCEEDED` error code);
  * median/mean duration and mean tool calls;
  * a usefulness score (a bounded, explainable blend of the above);
  * a deprecation recommendation when a version is failing or unused;
  * a promotion-evidence summary an operator can read before approving.

Nothing here promotes a skill. It only reports; promotion stays evaluation +
operator gated.
"""

from __future__ import annotations

from typing import Any, Optional

_TOOL_BUDGET_CODES = frozenset({"TOOL_BUDGET_EXCEEDED", "TOOL_BUDGET"})
_MIN_USEFUL_SAMPLE = 3


def _error_code(execution: dict[str, Any]) -> str:
    error = execution.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "")
    return ""


def _is_tool_budget_failure(execution: dict[str, Any]) -> bool:
    if execution.get("status") == "completed":
        return False
    code = _error_code(execution)
    if code in _TOOL_BUDGET_CODES:
        return True
    # Some paths report the budget failure through warnings/metrics rather than
    # the error code; accept that signal too.
    warnings = execution.get("warnings") or []
    return any("tool budget" in str(w).lower() for w in warnings)


def skill_quality_metrics(
    store: Any,
    skill_id: str,
    *,
    version: Optional[str] = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Compute usefulness metrics for a skill (optionally one version).

    Returns an honest report even with zero executions: every rate is None (not
    0) when there is no sample, so "never used" is never rendered as "always
    fails".
    """
    executions = [
        e for e in store.list_executions(skill_id, limit=limit)
        if version is None or e.get("version") == version
    ]
    total = len(executions)
    completed = [e for e in executions if e.get("status") == "completed"]
    failed = [e for e in executions if e.get("status") not in ("completed", "running")]
    validated = [e for e in executions if e.get("outputValidated") is True]
    invalid = [e for e in completed if e.get("outputValidated") is False]
    tool_budget = [e for e in executions if _is_tool_budget_failure(e)]

    durations = [int(e.get("durationMs") or 0) for e in executions if e.get("durationMs")]
    tool_calls = [
        int((e.get("metrics") or {}).get("toolCalls") or 0)
        for e in executions if isinstance(e.get("metrics"), dict)
    ]

    def _rate(numerator: int, denominator: int) -> Optional[float]:
        return round(numerator / denominator, 3) if denominator else None

    metrics: dict[str, Any] = {
        "skillId": skill_id,
        "version": version,
        "executions": total,
        "completed": len(completed),
        "failed": len(failed),
        "successRate": _rate(len(completed), total),
        "failureRate": _rate(len(failed), total),
        "outputValidationRate": _rate(len(validated), total),
        "invalidOutputCount": len(invalid),
        "toolBudgetFailureRate": _rate(len(tool_budget), total),
        "meanDurationMs": round(sum(durations) / len(durations)) if durations else None,
        "meanToolCalls": round(sum(tool_calls) / len(tool_calls), 2) if tool_calls else None,
    }
    metrics["usefulness"] = _usefulness_score(metrics)
    metrics["deprecation"] = _deprecation_recommendation(metrics)
    return metrics


def _usefulness_score(metrics: dict[str, Any]) -> dict[str, Any]:
    """A bounded, explainable usefulness score in [0, 1].

    With no executions the score is None (unknown), never a fabricated 0. The
    blend rewards a successful, schema-valid, tool-budget-respecting execution.
    """
    if not metrics["executions"]:
        return {"score": None, "reason": "no executions recorded yet"}
    success = metrics["successRate"] or 0.0
    tool_ok = 1.0 - (metrics["toolBudgetFailureRate"] or 0.0)
    validation = metrics["outputValidationRate"] or 0.0
    score = round(0.5 * success + 0.3 * validation + 0.2 * tool_ok, 3)
    return {
        "score": score,
        "reason": (
            f"success {success:.2f} · output-validation {validation:.2f} · "
            f"tool-budget-ok {tool_ok:.2f}"
        ),
    }


def _deprecation_recommendation(metrics: dict[str, Any]) -> dict[str, Any]:
    """Recommend deprecation when a version clearly underperforms. Advisory only."""
    if metrics["executions"] < _MIN_USEFUL_SAMPLE:
        return {"recommend": False, "reason": "not enough executions to judge"}
    if (metrics["failureRate"] or 0) >= 0.5:
        return {"recommend": True, "reason": "failure rate at or above 50%"}
    if (
        (metrics["toolBudgetFailureRate"] or 0) >= 0.4
    ):
        return {"recommend": True, "reason": "tool-budget failures at or above 40%"}
    if metrics["outputValidationRate"] == 0.0 and metrics["successRate"] == 1.0:
        return {"recommend": True, "reason": "runs complete but no output ever validates"}
    return {"recommend": False, "reason": "within expected range"}


def compare_versions(
    store: Any,
    skill_id: str,
    older: str,
    newer: str,
) -> dict[str, Any]:
    """Regression comparison across two versions: did any metric get worse?"""
    before = skill_quality_metrics(store, skill_id, version=older)
    after = skill_quality_metrics(store, skill_id, version=newer)
    regressions: list[str] = []
    for key in ("successRate", "outputValidationRate"):
        b, a = before.get(key), after.get(key)
        if b is not None and a is not None and a < b:
            regressions.append(f"{key}: {b} -> {a}")
    tb_before, tb_after = before.get("toolBudgetFailureRate"), after.get("toolBudgetFailureRate")
    if tb_before is not None and tb_after is not None and tb_after > tb_before:
        regressions.append(f"toolBudgetFailureRate: {tb_before} -> {tb_after}")
    return {
        "skillId": skill_id, "older": older, "newer": newer,
        "before": before, "after": after,
        "regressions": regressions, "regressed": bool(regressions),
    }


def promotion_evidence(store: Any, skill_id: str, version: str) -> dict[str, Any]:
    """The evidence an operator should see before promoting a version.

    Combines the deterministic evaluation (if any) with the real execution metrics
    and an explicit statement that recommendation is advisory, never automatic.
    """
    evaluations = [
        e for e in store.list_evaluations(skill_id, limit=50) if e["version"] == version
    ]
    latest = evaluations[0] if evaluations else None
    metrics = skill_quality_metrics(store, skill_id, version=version)
    return {
        "skillId": skill_id,
        "version": version,
        "evaluation": {
            "status": (latest or {}).get("status"),
            "summary": (latest or {}).get("summary"),
            "dimensions": (latest or {}).get("dimensions", []),
        } if latest else None,
        "executionMetrics": metrics,
        "deprecation": metrics["deprecation"],
        "usefulness": metrics["usefulness"],
        "note": "Advisory evidence only. Promotion remains evaluation- and operator-gated; "
                "this never enables or promotes a skill.",
    }


__all__ = [
    "compare_versions",
    "promotion_evidence",
    "skill_quality_metrics",
]
