"""Model arena — compare families on the SAME dataset and the SAME folds.

The arena answers the question that follows "build me a model": *which* model.
It never trains a different validation design for a different family — every run
uses the caller's one split spec, one seed and one dataset version, so a
comparison cannot be won by an easier fold.

Honesty rules:

  * a metric that was not measured is `None` and is EXCLUDED from the ranking; it
    is never read as zero;
  * a failed/cancelled run appears in the table with its status and reason, and
    cannot be ranked;
  * a task without ground truth (`anomaly`) is NOT ranked at all — the table is
    returned with that stated;
  * a winner whose margin is inside the fold-to-fold noise is reported as "no
    clear winner", with the numbers that justify it.
"""

from __future__ import annotations

from typing import Any, Optional

# Primary metric + direction per task. Absent = the task is not rankable.
PRIMARY_METRIC: dict[str, tuple[str, str]] = {
    "classification": ("macroF1", "higher"),
    "regression": ("rmse", "lower"),
    "clustering": ("silhouette", "higher"),
}

# Secondary order, used only to break an exact tie. (key, direction) pairs.
SECONDARY_METRICS: dict[str, tuple[tuple[str, str], ...]] = {
    "classification": (("rocAuc", "higher"), ("balancedAccuracy", "higher"),
                       ("accuracy", "higher")),
    "regression": (("mae", "lower"), ("r2", "higher")),
    "clustering": (("inertia", "lower"),),
}

MAX_FAMILIES = 6


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and value == value else None


def _value(row: dict[str, Any], key: str) -> Optional[float]:
    pooled = row.get("pooledMetrics") or {}
    value = _number(pooled.get(key))
    return value if value is not None else _number((row.get("foldMetricsMean") or {}).get(key))


def build_comparison(runs: list[dict[str, Any]], task: str) -> dict[str, Any]:
    """The comparison table + an honest verdict for one arena run."""
    rows: list[dict[str, Any]] = []
    for run in runs:
        result = run.get("result") or {}
        rows.append({
            "modelFamily": result.get("modelFamily") or run.get("modelFamily"),
            "runId": run.get("runId"),
            "status": run.get("status", "completed"),
            "error": run.get("error"),
            "task": result.get("task") or task,
            "pooledMetrics": result.get("pooledMetrics") or {},
            "foldMetricsMean": result.get("foldMetricsMean") or {},
            "foldMetricsStd": result.get("foldMetricsStd") or {},
        })

    spec = PRIMARY_METRIC.get(task)
    if spec is None:
        return {
            "task": task, "rows": rows, "primaryMetric": None, "ranking": [],
            "winner": None,
            "note": ("this task has no ground truth, so no family is 'better' — the "
                     "table reports out-of-sample rates and scores only, never a ranking"),
        }

    metric, direction = spec
    ranked: list[dict[str, Any]] = []
    unmeasured: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] != "completed":
            unmeasured.append({"modelFamily": row["modelFamily"], "reason": row["status"],
                               "detail": row["error"]})
            continue
        value = _value(row, metric)
        if value is None:
            unmeasured.append({"modelFamily": row["modelFamily"],
                               "reason": "unmeasured", "detail": f"{metric} is null for this run"})
            continue
        ranked.append({"modelFamily": row["modelFamily"],
                       "runId": row["runId"], "value": value,
                       "std": _number((row["foldMetricsStd"] or {}).get(metric))})

    def sort_key(item: dict[str, Any]) -> tuple[float, ...]:
        # Ascending sort: negate a "higher is better" value so the best leads.
        primary = item["value"] if direction == "lower" else -item["value"]
        row = next(r for r in rows if r["runId"] == item["runId"])
        tie_breaks: list[float] = []
        for key, tie_direction in SECONDARY_METRICS.get(task, ()):
            val = _value(row, key)
            if val is None:
                continue
            tie_breaks.append(val if tie_direction == "lower" else -val)
        return (primary, *tie_breaks)

    ranked.sort(key=sort_key)
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position

    winner = None
    note = ""
    if not ranked:
        note = "no run produced a comparable metric, so there is no winner"
    elif len(ranked) == 1:
        winner = ranked[0]
        note = (f"only {winner['modelFamily']} produced {metric}; there is nothing to "
                "compare it against")
    else:
        best, second = ranked[0], ranked[1]
        margin = abs(best["value"] - second["value"])
        noise = max(best["std"] or 0.0, second["std"] or 0.0)
        if noise > 0 and margin <= noise:
            note = (f"{best['modelFamily']} and {second['modelFamily']} are within fold "
                    f"noise on {metric} (margin {margin:.4g} <= spread {noise:.4g}) — "
                    "treat this as no clear winner")
        else:
            winner = best
            note = (f"{best['modelFamily']} leads on {metric} by {margin:.4g} "
                    f"({best['value']:.4g} vs {second['value']:.4g})")

    return {
        "task": task, "primaryMetric": {"key": metric, "direction": direction},
        "rows": rows, "ranking": ranked, "unmeasured": unmeasured,
        "winner": winner, "note": note,
    }


__all__ = ["MAX_FAMILIES", "PRIMARY_METRIC", "build_comparison"]
