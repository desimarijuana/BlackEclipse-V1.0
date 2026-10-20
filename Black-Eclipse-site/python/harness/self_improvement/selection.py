"""Deterministic anonymous selection for recursive RSL experiments.

Selection answers one question: which independently verified candidate should
be considered for composition? It does not adopt anything. Candidates are
renamed to stable anonymous labels with a seeded shuffle, non-answers are
dropped with a recorded cause, and an empty pool falls back neutrally to the
base. `k=1` is the trivial path and never opens a selector session.

The selection record is evidence, not a verdict: it carries no raw grader text
and passes the evaluation verdict tripwire before it is returned.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Mapping, Optional, Sequence

from ..evaluation.verdict_guard import assert_text_has_no_verdict_leaks

BASE_LABEL = "base"


def anonymous_labels(ids: Sequence[str], *, seed: int = 0) -> dict[str, str]:
    """Seeded anonymization: stable for a seed, a permutation of the pool.

    Sorting before the shuffle makes the assignment independent of proposal
    order (so a re-run cannot leak position), while the seed keeps it
    reproducible.
    """
    ordered = sorted({str(item) for item in ids if str(item)})
    random.Random(int(seed)).shuffle(ordered)
    labels: dict[str, str] = {}
    for index, item in enumerate(ordered):
        label = chr(ord("A") + index) if index < 26 else f"V{index + 1}"
        labels[item] = label
    return labels


def result_score(result: Any) -> Optional[float]:
    """A real measured score from a verification result, or None.

    `verify_surface` stores the acceptance target in its decision record; a
    tests-only code verification carries no score by design.
    """
    if not isinstance(result, Mapping):
        return None
    score = result.get("score")
    if score is None:
        decision = result.get("decisionRecord")
        if isinstance(decision, Mapping):
            score = decision.get("targetAfter")
    if score is None:
        return None
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def _summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": candidate.get("kind"),
        "targetPath": candidate.get("targetPath"),
        "opsCount": len(candidate.get("ops") or []),
        "benchmark": candidate.get("benchmark") or "UNMEASURED",
    }


def build_selection(
    candidates: Sequence[Mapping[str, Any]],
    *,
    seed: int = 0,
    base_label: str = BASE_LABEL,
) -> dict[str, Any]:
    """Build the deterministic selection record.

    Each candidate may carry: `id`, `kind`, `targetPath`, `ops`, `answered`,
    `passed`, `score`, `benchmark` and `cause`. An unanswered candidate is
    dropped with its cause; an answered-but-rejected candidate is recorded as
    rejected. The chosen candidate is the unique best measured score when one
    exists, otherwise the lowest anonymous label (a deterministic tie-break, not
    a claim that it is better).
    """
    items = [dict(candidate) for candidate in candidates or []]
    labels = anonymous_labels([str(item.get("id") or "") for item in items], seed=seed)
    for item in items:
        item["label"] = labels.get(str(item.get("id") or ""), BASE_LABEL)

    dropped: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    for item in items:
        answered = item.get("answered") is not False and item.get("passed") is not None
        if not answered:
            dropped.append({
                "id": item.get("id"),
                "label": item.get("label"),
                "cause": str(item.get("cause") or "no_answer"),
            })
        elif not item.get("passed"):
            rejected.append({
                "id": item.get("id"),
                "label": item.get("label"),
                "cause": str(item.get("cause") or "not_verified"),
            })
        else:
            verified.append(item)

    chosen: Optional[dict[str, Any]] = None
    fallback = False
    if not verified:
        fallback = True
        why = "no verified candidate; neutral fallback to the base"
    elif len(verified) == 1:
        chosen = verified[0]
        why = "one verified candidate; no selector session"
    else:
        scored = [item for item in verified if item.get("score") is not None]
        if scored:
            best = max(float(item["score"]) for item in scored)
            tied = [item for item in scored if float(item["score"]) == best]
            chosen = min(tied, key=lambda item: str(item.get("label") or ""))
            why = (
                "highest measured score; tie broken deterministically by "
                "anonymous label"
                if len(tied) > 1
                else "highest measured score"
            )
        else:
            chosen = min(verified, key=lambda item: str(item.get("label") or ""))
            why = "deterministic first verified candidate (no selector session)"

    chosen_label = str(chosen.get("label")) if chosen else base_label
    record = {
        "kind": "rsl-selection",
        "seed": int(seed),
        "k": len(items),
        "trivial": len(items) == 1,
        "nCandidates": len(verified),
        "chosen": str(chosen.get("id")) if chosen else base_label,
        "chosenLabel": chosen_label,
        "fallback": fallback,
        "why": why,
        "benchmark": (chosen.get("benchmark") if chosen else None) or "UNMEASURED",
        "dropped": dropped,
        "rejected": rejected,
        "idMap": {
            str(item.get("label")): _summary(item)
            for item in items
            if item.get("id") is not None
        },
        "evidence": "selection-record",
    }
    assert_text_has_no_verdict_leaks(
        json.dumps(record, sort_keys=True, default=str),
        label="selection",
    )
    return record


def selection_digest(record: Mapping[str, Any]) -> str:
    """A stable digest of the selection for an experiment record."""
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "BASE_LABEL",
    "anonymous_labels",
    "build_selection",
    "result_score",
    "selection_digest",
]
