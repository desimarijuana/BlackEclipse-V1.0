"""Structured source-conflict engine (Universal Financial Data Accuracy, §13/§26).

When two facts disagree, do NOT silently pick one. Produce a `FactConflict` that
names both sources, their definitions, the period, the difference, a likely
explanation, a preferred value (only when a rule justifies one) and a confidence.

Crucially, two numbers can BOTH be correct: consolidated net income vs
parent-attributable net income are different accounting definitions, not an
error. That case is marked `semantic=True` and the answer explains the
difference rather than declaring one wrong — semantic reconciliation, not
numerical suppression.

This reuses the existing relative-tolerance idea from `retrieval/conflicts.py`
(0.5%) but emits the richer record this engine requires.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .model import FactConflict
from .semantics import definitions_differ
from .ttm import _numeric  # a fact's numeric value, or None (never fabricates)

DEFAULT_REL_TOLERANCE = 0.005  # 0.5%, matching retrieval/conflicts.py

# Source-type authority order used ONLY as a tie-break of last resort, and said so.
_TIER_RANK: dict[str, int] = {
    "regulatory_filing": 7,
    "exchange_filing": 7,
    "company_report": 6,
    "investor_relations": 6,
    "government": 5,
    "financial_database": 4,
    "market_data": 4,
    "aggregator": 3,
    "vault": 2,
    "derived": 2,
    "unknown": 0,
}


def _close(a: float, b: float, rel: float = DEFAULT_REL_TOLERANCE) -> bool:
    if a == b:
        return True
    return abs(a - b) / max(abs(a), abs(b), 1e-9) <= rel


def _period_key(fact) -> Optional[str]:
    period = getattr(fact, "period", None)
    if period is None:
        return None
    try:
        return period.key()
    except Exception:  # noqa: BLE001 - a malformed period is not a comparison key
        return None


def detect_conflict(a, b, *, rel_tolerance: float = DEFAULT_REL_TOLERANCE) -> Optional[FactConflict]:
    """Compare two facts. Returns a FactConflict when they differ, else None.

    Two facts are only comparable when they are about the SAME fact:
      * same metric, AND
      * the same period (a bar at another date is a DIFFERENT observation, not a
        disagreement — the bug the scenario tests caught), AND
      * different sources (a source cannot disagree with itself).

    `a` and `b` are FinancialFact-like objects (metric, value, definition, period,
    source, source_type).
    """
    # Same concept: either the same raw metric, or the same resolved accounting
    # definition (so "total revenue" and "revenue" that both resolve to `revenue`
    # are comparable).
    same_concept = a.metric == b.metric or (
        getattr(a, "definition", None) is not None
        and getattr(a, "definition", None) == getattr(b, "definition", None)
    )
    if not same_concept:
        return None

    # A different period is a separate observation, never a conflict.
    if _period_key(a) != _period_key(b):
        return None

    # A single source repeating itself (same source, same period) is not a
    # conflict — it is a duplicate.
    if getattr(a, "source", None) and getattr(a, "source", None) == getattr(b, "source", None):
        return None

    va, vb = _numeric(a), _numeric(b)
    period_label = _period_key(a)

    defs_differ = definitions_differ(getattr(a, "definition", None), getattr(b, "definition", None))

    # Non-numeric facts, or one side missing: not a numeric conflict.
    if va is None or vb is None:
        if getattr(a, "value", None) == getattr(b, "value", None):
            return None
        return FactConflict(
            metric=a.metric, source_a=str(a.source), source_b=str(b.source), period=period_label,
            definition_a=a.definition, definition_b=b.definition, value_a=a.value, value_b=b.value,
            difference=None, relative_difference=None,
            explanation="non-numeric or partially missing values differ",
            semantic=defs_differ, confidence="low",
        )

    if defs_differ:
        # §26: different definitions, both possibly correct. Do NOT call this error.
        return FactConflict(
            metric=a.metric, source_a=str(a.source), source_b=str(b.source), period=period_label,
            definition_a=a.definition, definition_b=b.definition, value_a=va, value_b=vb,
            difference=va - vb, relative_difference=abs(va - vb) / max(abs(va), abs(vb), 1e-9),
            explanation="the two sources report DIFFERENT accounting definitions of this metric; "
                        "both can be correct — this is a definition difference, not necessarily an error",
            semantic=True, confidence="medium",
        )

    if _close(va, vb, rel_tolerance):
        return None  # agreement (within tolerance) is not a conflict

    diff = va - vb
    rel = abs(diff) / max(abs(va), abs(vb), 1e-9)

    # Same definition, genuinely different numbers. Try to explain by SOURCE
    # authority, and say the reason; otherwise flag for investigation.
    rank_a = _TIER_RANK.get(getattr(a, "source_type", "unknown"), 0)
    rank_b = _TIER_RANK.get(getattr(b, "source_type", "unknown"), 0)
    if rank_a != rank_b:
        preferred = "a" if rank_a > rank_b else "b"
        winner = a if rank_a > rank_b else b
        return FactConflict(
            metric=a.metric, source_a=str(a.source), source_b=str(b.source), period=period_label,
            definition_a=a.definition, definition_b=b.definition, value_a=va, value_b=vb,
            difference=diff, relative_difference=rel,
            explanation="same definition, different values; the more authoritative source is preferred",
            preferred=preferred,
            reason=f"{winner.source} is a more authoritative source type for this fact",
            confidence="medium",
        )

    return FactConflict(
        metric=a.metric, source_a=str(a.source), source_b=str(b.source), period=period_label,
        definition_a=a.definition, definition_b=b.definition, value_a=va, value_b=vb,
        difference=diff, relative_difference=rel,
        explanation="same definition, same authority, different values — investigate before using either",
        preferred=None, reason=None, confidence="low",
    )


def reconcile(facts: Sequence, *, rel_tolerance: float = DEFAULT_REL_TOLERANCE) -> tuple[Optional[object], list[FactConflict]]:
    """Reduce a group of same-metric facts to (chosen_or_None, conflicts).

    The chosen fact is returned ONLY when the group agrees (after removing any
    semantically-different definitions, which are never merged). When the group
    conflicts numerically, no fact is chosen — every conflict is returned so the
    caller surfaces the disagreement rather than suppressing it.
    """
    usable = [f for f in facts if _numeric(f) is not None or getattr(f, "value", None) is not None]
    if not usable:
        return None, []
    if len(usable) == 1:
        return usable[0], []

    conflicts: list[FactConflict] = []
    chosen = usable[0]
    for other in usable[1:]:
        c = detect_conflict(chosen, other, rel_tolerance=rel_tolerance)
        if c is not None:
            conflicts.append(c)

    # If any conflict is a genuine same-definition numeric disagreement, choose none.
    hard = [c for c in conflicts if not c.semantic and c.preferred is None]
    if hard:
        return None, conflicts
    return chosen, conflicts


__all__ = ["DEFAULT_REL_TOLERANCE", "detect_conflict", "reconcile"]
