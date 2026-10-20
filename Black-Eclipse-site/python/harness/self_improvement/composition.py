"""Deterministic composition of independently verified RSL candidates.

Composition never trusts a claim: only candidates that passed their own
verification can be merged. Merging is conservative — overlapping file paths
conflict and refuse the merge. A merged candidate is accepted only when it is
MEASURED on validation and beats the best single verified candidate; otherwise
the honest result is `no_gain`.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable, Mapping, Optional, Sequence

from ..evaluation.verdict_guard import assert_text_has_no_verdict_leaks

Measurement = Callable[[dict[str, Any]], Any]


def _verified(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(candidate) for candidate in candidates or []
        if candidate.get("passed") is True and candidate.get("answered") is not False
    ]


def _op_paths(op: Mapping[str, Any]) -> set[str]:
    return {
        str(op[key]) for key in ("path", "fromPath")
        if op.get(key)
    }


def merge_verified_ops(
    candidates: Sequence[Mapping[str, Any]],
) -> Optional[list[dict[str, Any]]]:
    """Merge non-conflicting verified ops, or None on a conflict.

    Two candidates conflict when any operation path (including a move source)
    appears in both. That is the conservative rule: a shared file means the
    changes cannot be independently composed without a real three-way merge,
    which R7 does not invent.
    """
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        ops = candidate.get("ops") or []
        if not ops:
            return None
        for op in ops:
            if not isinstance(op, Mapping):
                return None
            paths = _op_paths(op)
            if not paths or paths & seen:
                return None
            seen |= paths
            merged.append(dict(op))
    return merged or None


def best_single(candidates: Sequence[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """The deterministic best verified candidate (measured score, else label)."""
    scored = [item for item in candidates if item.get("score") is not None]
    if scored:
        best = max(float(item["score"]) for item in scored)
        tied = [item for item in scored if float(item["score"]) == best]
        return min(tied, key=lambda item: str(item.get("label") or ""))
    if not candidates:
        return None
    return min(candidates, key=lambda item: str(item.get("label") or ""))


def _guard(record: dict[str, Any]) -> dict[str, Any]:
    assert_text_has_no_verdict_leaks(
        json.dumps(record, sort_keys=True, default=str),
        label="composition",
    )
    return record


async def compose_verified(
    candidates: Sequence[Mapping[str, Any]],
    *,
    measure: Optional[Measurement] = None,
) -> dict[str, Any]:
    """Select the best verified candidate or a measured composition.

    `measure` is the caller's validation hook (the real evaluator for a surface
    candidate). It is only ever called on ops from verified candidates. Without
    it a merge can never claim a gain, so the result is `no_gain`.
    """
    verified = _verified(candidates)
    if not verified:
        return _guard({
            "kind": "rsl-composition",
            "decision": "no_verified",
            "benchmark": "UNMEASURED",
            "reason": "no candidate passed verification; nothing is composed",
            "chosenLabel": None,
        })

    best = best_single(verified)
    if len(verified) == 1:
        return _guard({
            "kind": "rsl-composition",
            "decision": "selected",
            "benchmark": best.get("benchmark") or "UNMEASURED",
            "reason": "one verified candidate; selection is not a composition claim",
            "chosenLabel": best.get("label"),
            "chosenId": best.get("id"),
            "composedOps": None,
        })

    merged = merge_verified_ops(verified)
    if merged is None:
        return _guard({
            "kind": "rsl-composition",
            "decision": "selected",
            "benchmark": best.get("benchmark") or "UNMEASURED",
            "reason": "verified ops overlap; no non-conflicting merge exists",
            "chosenLabel": best.get("label"),
            "chosenId": best.get("id"),
            "composedOps": None,
        })

    composed = {
        "kind": "invariant",
        "targetPath": verified[0].get("targetPath"),
        "ops": merged,
        "description": "composed verified RSL ops",
        "labels": [item.get("label") for item in verified],
    }
    if measure is None:
        return _guard({
            "kind": "rsl-composition",
            "decision": "no_gain",
            "benchmark": "UNMEASURED",
            "reason": "no validation measurement for the composed candidate",
            "chosenLabel": best.get("label"),
            "composedOps": merged,
            "composed": composed,
        })

    result = measure(composed)
    if inspect.isawaitable(result):
        result = await result
    result = result if isinstance(result, Mapping) else {}
    benchmark = str(result.get("benchmark") or "UNMEASURED").upper()
    passed = bool(result.get("passed"))
    composed_score = result.get("score")
    if composed_score is None:
        decision_record = result.get("decisionRecord")
        if isinstance(decision_record, Mapping):
            composed_score = decision_record.get("targetAfter")
    try:
        composed_score = float(composed_score) if composed_score is not None else None
    except (TypeError, ValueError):
        composed_score = None
    best_score = best.get("score")
    try:
        best_score = float(best_score) if best_score is not None else None
    except (TypeError, ValueError):
        best_score = None

    if not passed:
        decision, reason = "no_gain", "the composed candidate did not pass verification"
    elif benchmark != "MEASURED":
        decision, reason = "no_gain", "the composed candidate is UNMEASURED"
    elif best_score is None:
        decision, reason = "no_gain", "no measured single-candidate baseline exists"
    elif composed_score is None:
        decision, reason = "no_gain", "the composed run reported no measured score"
    elif composed_score <= best_score:
        decision, reason = (
            "no_gain",
            "the composed candidate did not beat the best single candidate",
        )
    else:
        decision, reason = "composed", "the composed candidate beat the best single candidate"

    return _guard({
        "kind": "rsl-composition",
        "decision": decision,
        "benchmark": "MEASURED" if decision == "composed" else "UNMEASURED",
        "reason": reason,
        "chosenLabel": best.get("label") if decision != "composed" else "composed",
        "composedScore": composed_score,
        "bestSingleScore": best_score,
        "composedOps": merged,
        "composed": composed,
    })


__all__ = [
    "Measurement",
    "best_single",
    "compose_verified",
    "merge_verified_ops",
]
