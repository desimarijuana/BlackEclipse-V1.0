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

import math
from typing import Any, Optional

_TOOL_BUDGET_CODES = frozenset({"TOOL_BUDGET_EXCEEDED", "TOOL_BUDGET"})
_MIN_USEFUL_SAMPLE = 3
# Below this many executions a rate is reported as "low sample" and must not be
# presented as statistically reliable.
_RELIABLE_SAMPLE = 20

# Failure-cause buckets, derived deterministically from existing execution
# fields (error code, warnings) — never model-guessed. Mirrors the vocabulary
# used by the mistake detector where possible.
FAILURE_CAUSES = (
    "missing_tool", "invalid_input", "output_validation", "unsupported_data",
    "timeout", "permission_denied", "user_correction", "provider_failure",
    "tool_budget", "unknown",
)


def _failure_cause(execution: dict[str, Any]) -> Optional[str]:
    """Classify WHY an execution failed, from its stored fields only."""
    if execution.get("status") == "completed":
        return None
    code = _error_code(execution).upper()
    text = " ".join([
        code,
        " ".join(str(w) for w in (execution.get("warnings") or [])),
        " ".join(str(x) for x in (execution.get("missingData") or [])),
    ]).lower()
    if code in _TOOL_BUDGET_CODES or "tool budget" in text:
        return "tool_budget"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "permission" in text or "denied" in text or "forbidden" in text:
        return "permission_denied"
    if "tool_unavailable" in text or "missing tool" in text or "tool not found" in text or "unknown tool" in text:
        return "missing_tool"
    if "input_validation" in text or "invalid input" in text or "schema" in text:
        return "invalid_input"
    if "output" in text and ("valid" in text or "shape" in text):
        return "output_validation"
    if "not_covered" in text or "unsupported" in text or "unavailable" in text or "no data" in text:
        return "unsupported_data"
    if "provider" in text or "source_unavailable" in text or "upstream" in text:
        return "provider_failure"
    if "correction" in text:
        return "user_correction"
    return "unknown"


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> Optional[tuple[float, float]]:
    """A 95% Wilson score interval for a proportion. None when no sample."""
    if total <= 0:
        return None
    phat = successes / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return (round(max(0.0, low), 3), round(min(1.0, high), 3))


def _daily_trend(executions: list[dict[str, Any]], days: int = 14) -> list[dict[str, Any]]:
    """A bounded per-day success/total series (oldest first). Derived only."""
    buckets: dict[str, dict[str, int]] = {}
    for execution in executions:
        created = str(execution.get("createdAt") or "")[:10]
        if not created:
            continue
        bucket = buckets.setdefault(created, {"total": 0, "completed": 0})
        bucket["total"] += 1
        if execution.get("status") == "completed":
            bucket["completed"] += 1
    series = [
        {"day": day, "total": b["total"], "completed": b["completed"],
         "successRate": round(b["completed"] / b["total"], 3) if b["total"] else None}
        for day, b in sorted(buckets.items())
    ]
    return series[-days:]


def _time_weighted_success(executions: list[dict[str, Any]]) -> Optional[float]:
    """A recency-weighted success rate (newer executions weigh more).

    Uses a simple linear weight over the most-recent-first ordering so recent
    regressions are visible sooner than a flat average would show.
    """
    if not executions:
        return None
    ordered = sorted(
        executions, key=lambda e: str(e.get("createdAt") or ""), reverse=True,
    )
    weight_sum = 0.0
    weighted = 0.0
    for index, execution in enumerate(ordered):
        weight = 1.0 / (1.0 + index)  # harmonic recency weight
        weight_sum += weight
        if execution.get("status") == "completed":
            weighted += weight
    return round(weighted / weight_sum, 3) if weight_sum else None


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
    # Failure-cause clustering (deterministic, from stored fields only).
    causes: dict[str, int] = {}
    for execution in failed:
        cause = _failure_cause(execution) or "unknown"
        causes[cause] = causes.get(cause, 0) + 1
    metrics["failureCauses"] = causes

    # Sample-size honesty: a rate with too few samples is flagged, and success
    # carries a 95% Wilson interval so a small sample is not read as reliable.
    metrics["sampleReliable"] = total >= _RELIABLE_SAMPLE
    metrics["successInterval"] = _wilson_interval(len(completed), total)
    if total and total < _RELIABLE_SAMPLE:
        metrics["sampleWarning"] = (
            f"only {total} execution(s) recorded — rates are not statistically reliable "
            f"(need >= {_RELIABLE_SAMPLE})"
        )
    else:
        metrics["sampleWarning"] = None

    # Trend + recency weighting.
    metrics["trend"] = _daily_trend(executions)
    metrics["timeWeightedSuccessRate"] = _time_weighted_success(executions)

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


def _evaluation_cases_by_id(store: Any, skill_id: str, version: str) -> dict[str, dict[str, Any]]:
    """The evaluation cases and their results for a version, keyed by caseId.

    Prefers the latest EVALUATION's recorded case results (with status); falls
    back to the version-attached case definitions when no evaluation has run.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        evaluations = [
            e for e in store.list_evaluations(skill_id, limit=50)
            if str(e.get("version")) == version
        ]
        if evaluations:
            latest_id = evaluations[0].get("id")
            full = store.get_evaluation(latest_id) if latest_id else None
            for case in (full or {}).get("cases") or []:
                out[str(case.get("caseId"))] = case
    except Exception:  # noqa: BLE001 - a missing evaluation is an empty map
        pass
    if not out:
        try:
            for case in store.list_evaluation_cases(skill_id, version):
                out[str(case.get("caseId"))] = case
        except Exception:  # noqa: BLE001
            pass
    return out


def compare_evaluation_cases(
    store: Any, skill_id: str, older: str, newer: str,
) -> dict[str, Any]:
    """Compare two versions on the SAME evaluation cases (reproducible).

    Reports `added`/`removed` cases and any case whose outcome changed from
    passing to failing (`regressed`). Deterministic; no model.
    """
    before = _evaluation_cases_by_id(store, skill_id, older)
    after = _evaluation_cases_by_id(store, skill_id, newer)
    shared = sorted(set(before) & set(after))
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    regressed: list[dict[str, str]] = []
    for case_id in shared:
        b_status = str(before[case_id].get("status") or "")
        a_status = str(after[case_id].get("status") or "")
        if b_status == "passed" and a_status and a_status != "passed":
            regressed.append({"caseId": case_id, "before": b_status, "after": a_status})
    return {
        "skillId": skill_id, "older": older, "newer": newer,
        "sharedCases": shared, "addedCases": added, "removedCases": removed,
        "caseRegressions": regressed,
        "comparable": bool(shared),
    }


def compare_versions(
    store: Any,
    skill_id: str,
    older: str,
    newer: str,
) -> dict[str, Any]:
    """Regression comparison across two versions: did any metric get worse?

    Includes both execution-metric regressions and same-evaluation-case
    regressions, plus sample-size honesty for each version.
    """
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
    case_comparison = compare_evaluation_cases(store, skill_id, older, newer)
    low_sample = [
        label for label, report in (("older", before), ("newer", after))
        if report.get("executions") and not report.get("sampleReliable")
    ]
    return {
        "skillId": skill_id, "older": older, "newer": newer,
        "before": before, "after": after,
        "caseComparison": case_comparison,
        "regressions": regressions, "regressed": bool(regressions) or bool(case_comparison["caseRegressions"]),
        "lowSampleVersions": low_sample,
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
        "sample": {
            "executions": metrics.get("executions", 0),
            "reliable": metrics.get("sampleReliable", False),
            "warning": metrics.get("sampleWarning"),
            "successInterval": metrics.get("successInterval"),
        },
        "trend": metrics.get("trend", []),
        "failureCauses": metrics.get("failureCauses", {}),
        "note": "Advisory evidence only. Promotion remains evaluation- and operator-gated; "
                "this never enables or promotes a skill.",
    }


def version_quality_history(store: Any, skill_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Per-version quality rows (newest first) for a trend view. Derived only."""
    versions: list[dict[str, Any]] = []
    try:
        for version in store.list_versions(skill_id)[:limit]:
            metrics = skill_quality_metrics(store, skill_id, version=version["version"])
            if metrics["executions"]:
                versions.append(metrics)
    except Exception:  # noqa: BLE001 - history must never raise
        return []
    return versions


__all__ = [
    "FAILURE_CAUSES",
    "compare_evaluation_cases",
    "compare_versions",
    "promotion_evidence",
    "skill_quality_metrics",
    "version_quality_history",
]
