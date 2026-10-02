"""Point-in-time / known-at analysis (Universal Financial Data Accuracy, §15).

For historical analysis Eclipse must not use information that was unavailable at
the historical date. This module keeps the three timestamps distinct:

    period_end            — the period the value is ABOUT
    publication_timestamp — when the source MADE IT PUBLIC (known_at)
    retrieved_timestamp   — when we fetched it

A FY2025 annual report published in February 2026 must NOT be used when
reconstructing what an analyst could have known in December 2025. A value with an
UNKNOWN publication time is never assumed available before its retrieval.

Pure functions over `FinancialFact`s; no I/O, no model.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .model import FinancialFact

# The time a fact became KNOWABLE at the earliest. Publication is the honest
# answer; when a source gives only a retrieval time, that is the earliest we can
# honestly claim to have known it — never earlier.
def known_at(fact: FinancialFact) -> Optional[str]:
    return fact.publication_timestamp or fact.retrieved_timestamp


def is_admissible_at(fact: FinancialFact, asof: Optional[str]) -> bool:
    """May this fact be used to reconstruct knowledge as of `asof`?

    No cutoff → always admissible. A fact with no knowable time is refused under a
    cutoff (we cannot prove it was known). Otherwise the fact is admissible only
    when its `known_at` is at or before the cutoff.
    """
    if not asof:
        return True
    stamp = known_at(fact)
    if not stamp:
        return False
    return str(stamp)[:19] <= str(asof)[:19]


def select_as_of(facts: Sequence[FinancialFact], asof: Optional[str]) -> list[FinancialFact]:
    """The facts admissible at `asof` (all of them when no cutoff is given)."""
    if not asof:
        return list(facts)
    return [f for f in facts if is_admissible_at(f, asof)]


def latest_known_per_metric(facts: Sequence[FinancialFact], asof: Optional[str]) -> dict[str, FinancialFact]:
    """For each metric, the most recently PUBLISHED fact admissible at `asof`.

    This is the point-in-time "what did we know then?" view: for a metric with a
    restatement, it returns the revision available by the cutoff, not the newest
    one that exists today.
    """
    out: dict[str, FinancialFact] = {}
    for fact in select_as_of(facts, asof):
        current = out.get(fact.metric)
        if current is None:
            out[fact.metric] = fact
            continue
        if _stamp(fact) > _stamp(current):
            out[fact.metric] = fact
    return out


def _stamp(fact: FinancialFact) -> str:
    return str(known_at(fact) or "")


__all__ = ["is_admissible_at", "known_at", "latest_known_per_metric", "select_as_of"]
