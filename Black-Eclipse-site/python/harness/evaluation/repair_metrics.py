"""Self-evolution metrics (round 4, W7) — measured or honestly unmeasured.

The §1 registry, each computed from REAL records or reported as `None` (never
fabricated):

| metric | source |
|---|---|
| `time_to_repair_ms` | resolved recovery incidents: median created → resolved |
| `self_repair_precision` | resolved incidents with a `succeeded` outcome / all resolved |
| `requirement_completeness` | goal-contract tasks: required criteria PASSED / required total |
| `cost_per_success` | evaluation trials: total recorded cost / passing trials |
| `unauthorized_action_rate` | evaluation trials: safety-grader failures / measured trials |

An unmeasured dimension is published as `UNMEASURED` in the gate report — the
capability statement never claims what it cannot measure.
"""

from __future__ import annotations

from typing import Any, Optional


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (float(ordered[middle - 1]) + float(ordered[middle])) / 2.0


def _moment(value: Any) -> Optional[float]:
    """ISO timestamp → epoch seconds, or None when unparseable."""
    if not value:
        return None
    import datetime as _dt  # noqa: PLC0415

    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def metrics_from_recovery(
    incidents: Optional[list[dict[str, Any]]],
    attempts_by_incident: Optional[dict[str, list[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """`time_to_repair_ms` + `self_repair_precision` from incident records.

    An incident qualifies for the timing when it is `resolved` and carries a
    resolution moment (`resolvedAt`/`updatedAt`, or the store row's
    `lastSeenAt`) later than its creation (`createdAt`/`firstSeenAt`).
    Precision counts only incidents with a recorded outcome — an explicit
    `outcome` field, or (the recovery store's real shape) the latest
    `action="outcome"` attempt.
    """
    durations: list[float] = []
    succeeded = 0
    decided = 0
    for incident in incidents or []:
        if str(incident.get("status")) != "resolved":
            continue
        outcome = str(incident.get("outcome") or "")
        if not outcome and attempts_by_incident is not None:
            for attempt in reversed(attempts_by_incident.get(str(incident.get("id")), [])):
                if str(attempt.get("action")) == "outcome":
                    outcome = str(attempt.get("outcome") or "")
                    break
        if outcome:
            decided += 1
            if outcome == "succeeded":
                succeeded += 1
        start = _moment(incident.get("createdAt") or incident.get("firstSeenAt"))
        end = _moment(
            incident.get("resolvedAt") or incident.get("updatedAt")
            or incident.get("lastSeenAt")
        )
        if start is not None and end is not None and end >= start:
            durations.append((end - start) * 1000.0)
    return {
        "time_to_repair_ms": _median(durations),
        "self_repair_precision": (succeeded / decided) if decided else None,
    }


def metrics_from_tasks(tasks: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    """`requirement_completeness` over goal-contract tasks.

    Each entry: `{"goalContract": {...}|None, "criteria": [{"required", "state"}]}`.
    Only tasks that carry a goal contract contribute — an ordinary task has no
    declared requirements to complete.
    """
    required_total = 0
    required_passed = 0
    for task in tasks or []:
        if not task.get("goalContract"):
            continue
        for criterion in task.get("criteria") or []:
            if not criterion.get("required", True):
                continue
            required_total += 1
            if str(criterion.get("state")) == "PASSED":
                required_passed += 1
    if required_total == 0:
        return {"requirement_completeness": None}
    return {"requirement_completeness": required_passed / required_total}


def metrics_from_suite(suite: Any) -> dict[str, Any]:
    """`cost_per_success` + `unauthorized_action_rate` from an evaluation suite."""
    cost = 0.0
    cost_known = True
    passed = 0
    measured = 0
    safety_failures = 0
    safety_samples = 0
    for task_result in getattr(suite, "tasks", []) or []:
        for trial in getattr(task_result, "trials", []) or []:
            if getattr(trial, "unmeasured", False):
                continue
            measured += 1
            score = getattr(trial, "score", None)
            trial_cost = getattr(score, "cost", None)
            if trial_cost is None:
                # A trial whose cost was never reported makes the total unknown;
                # a partial sum would be a fabricated number.
                cost_known = False
            else:
                cost += float(trial_cost)
            if getattr(trial, "passed", False):
                passed += 1
            for grader in getattr(score, "grader_results", []) or []:
                if str(grader.get("grader")) != "safety" or grader.get("unmeasured"):
                    continue
                safety_samples += 1
                if not grader.get("passed"):
                    safety_failures += 1
    return {
        "cost_per_success": (cost / passed) if passed and cost_known else None,
        "unauthorized_action_rate": (safety_failures / safety_samples) if safety_samples else None,
    }


def collect_self_evolution_metrics(
    *,
    suite: Any = None,
    incidents: Optional[list[dict[str, Any]]] = None,
    attempts_by_incident: Optional[dict[str, list[dict[str, Any]]]] = None,
    tasks: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """The full metric block; missing sources stay `None` (UNMEASURED)."""
    metrics: dict[str, Any] = {
        "time_to_repair_ms": None,
        "self_repair_precision": None,
        "requirement_completeness": None,
        "cost_per_success": None,
        "unauthorized_action_rate": None,
    }
    metrics.update(metrics_from_recovery(incidents, attempts_by_incident))
    metrics.update(metrics_from_tasks(tasks))
    if suite is not None:
        metrics.update(metrics_from_suite(suite))
    return metrics


__all__ = [
    "collect_self_evolution_metrics",
    "metrics_from_recovery",
    "metrics_from_suite",
    "metrics_from_tasks",
]
