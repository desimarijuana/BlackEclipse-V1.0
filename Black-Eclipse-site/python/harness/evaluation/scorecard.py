"""Generate scorecard metrics from a real evaluation run (C8.5).

The scorecard's numbers must come from runs, not from a human typing a value.
`regenerate` takes the curated dimension metadata (labels, weights, targets,
evidence paths) and fills `metric`/`status` only where an actual measurement
exists. A dimension with no measurement stays honest (`partial`/`unmeasured`)
and carries the reason.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional


def _aggregate(suite: Any, key: str) -> Optional[float]:
    aggregates = getattr(suite, "aggregates", None) or {}
    value = aggregates.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric(
    value: float, *, unit: str, direction: str, source: str,
    run_id: Optional[str], generated_at: str,
) -> dict[str, Any]:
    return {
        "value": round(value, 6),
        "unit": unit,
        "direction": direction,
        "source": source,
        "runId": run_id,
        "generatedAt": generated_at,
    }


def _measurements(
    suite: Any, release: Optional[dict[str, Any]], generated_at: str,
) -> dict[str, dict[str, Any]]:
    run_id = str(getattr(suite, "run_id", "") or "") or None
    source = "python -m harness.evaluation"
    measured: dict[str, dict[str, Any]] = {}
    task_success = _aggregate(suite, "task_success")
    if task_success is not None:
        measured["eval"] = _metric(task_success, unit="ratio", direction="higher",
                                   source=source, run_id=run_id, generated_at=generated_at)
    tool_accuracy = _aggregate(suite, "tool_accuracy")
    if tool_accuracy is not None:
        measured["aci"] = _metric(tool_accuracy, unit="ratio", direction="higher",
                                  source=source, run_id=run_id, generated_at=generated_at)
    safety = _aggregate(suite, "safety_score")
    if safety is not None:
        measured["safety"] = _metric(safety, unit="ratio", direction="higher",
                                     source=source, run_id=run_id, generated_at=generated_at)
    misroute = _aggregate(suite, "misroute_rate")
    if misroute is not None:
        measured["ext"] = _metric(misroute, unit="rate", direction="lower",
                                  source="deterministic routing benchmark", run_id=run_id,
                                  generated_at=generated_at)
    if release:
        runs = release.get("runs") or {}
        created = int(runs.get("created") or 0)
        terminal = int(runs.get("terminal") or 0)
        if created:
            measured["ops"] = _metric(
                min(1.0, terminal / created), unit="ratio", direction="higher",
                source="GET /observability/release-report (or C7 probe)",
                run_id=run_id, generated_at=generated_at,
            )
    return measured


def regenerate(
    base: dict[str, Any],
    *,
    suite: Any,
    release: Optional[dict[str, Any]] = None,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Return a scorecard with run-derived metrics; never invents a value."""
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = copy.deepcopy(base)
    result["generated"] = stamp
    measurements = _measurements(suite, release, stamp)
    for dimension in result.get("dimensions") or []:
        metric = measurements.get(str(dimension.get("id")))
        if metric is None:
            continue
        dimension["metric"] = metric
        dimension["status"] = "measured"
        note = str(dimension.get("note") or "").strip()
        generated_note = (
            f"Metric generated from run {metric.get('runId') or '(unrecorded)'} "
            f"at {stamp}; every measured dimension must carry a source."
        )
        dimension["note"] = f"{note} {generated_note}".strip()
    return result


__all__ = ["regenerate"]
