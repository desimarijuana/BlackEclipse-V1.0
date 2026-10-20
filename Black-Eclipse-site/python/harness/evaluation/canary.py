"""Pre-landing canary: the patched tree must hold on a second, disjoint task set.

Verification already proved an improvement on the validation split. A canary run
repeats the SAME patched tree on a different split (default `held_out`) and
requires that the target dimension does not regress beyond a small tolerance,
with the same critical-task veto. The result is evidence for the operator; it
does not land anything.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from .worktree_invoker import benchmark_decision


def _rate(result: Mapping[str, Any], dimension: str) -> Optional[float]:
    aggregates = result.get("aggregates") or {}
    value = aggregates.get(dimension)
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def assess_canary(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    target_dimension: str = "task_success",
    critical_tasks: Iterable[str] = (),
    tolerance: float = 0.0,
) -> dict[str, Any]:
    """Pass when the canary split is measured and does not regress beyond `tolerance`."""
    if not baseline.get("ok") or not candidate.get("ok"):
        return {
            "ok": False,
            "passed": False,
            "decision": "canary_unmeasured",
            "detail": (baseline.get("error") or candidate.get("error") or "suite failed"),
        }
    before = _rate(baseline, target_dimension)
    after = _rate(candidate, target_dimension)
    if before is None or after is None:
        return {
            "ok": False,
            "passed": False,
            "decision": "canary_unmeasured",
            "detail": f"{target_dimension} is UNMEASURED on the canary split",
        }
    # `min_improvement=-1` disables the improvement requirement; this module
    # only asks that the canary did not regress. Critical drops still veto.
    decision = benchmark_decision(
        baseline, candidate,
        target_dimension=target_dimension,
        min_improvement=-1.0,
        critical_tasks=critical_tasks,
    )
    drop = round(float(before) - float(after), 6)
    tolerated = drop <= float(tolerance)
    reasons = list(decision.get("reasons") or [])
    if not tolerated:
        reasons.append(
            f"canary target dropped {drop:.3f} (tolerance {float(tolerance):.3f})"
        )
    if not decision.get("accepted"):
        reasons.append("canary critical regression")
    return {
        "ok": True,
        "passed": bool(decision.get("accepted")) and tolerated,
        "decision": "canary_passed" if (decision.get("accepted") and tolerated)
        else "canary_rejected",
        "targetDimension": target_dimension,
        "before": before,
        "after": after,
        "drop": drop,
        "tolerance": float(tolerance),
        "reasons": reasons,
        "decisionRecord": decision,
    }


__all__ = ["assess_canary"]
