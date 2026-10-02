"""Evidence-based confidence model (Universal Financial Data Accuracy, §20).

Confidence is DERIVED from evidence, never an arbitrary LLM feeling. It is a
deterministic function of six inputs:

    source quality      — how authoritative the source type is for this fact
    freshness           — how current the fact is for its metric
    definition clarity  — is the accounting concept unambiguous?
    cross-source agreement — do independent sources agree?
    calculation integrity  — is a derived value reproducible? (reported = n/a)
    period alignment    — is the period explicit and comparable?

The result is HIGH / MEDIUM / LOW / UNVERIFIED. Any single missing pillar caps the
level; a hard failure (superseded, or a material conflict) drops it to LOW or
UNVERIFIED rather than being averaged away. Averaging is what hides a broken fact
behind five good ones.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import freshness as fresh
from .model import ConfidenceLevel, FinancialFact

# Source quality per source type (higher = more authoritative for a reported
# financial fact). This is the DEFAULT ranking; §1 says authority depends on the
# fact, so the market-price path overrides it (a live market feed beats a filing
# for a price — see `SOURCE_QUALITY` usage in confidence_for).
SOURCE_QUALITY: dict[str, int] = {
    "regulatory_filing": 5,
    "exchange_filing": 5,
    "company_report": 4,
    "investor_relations": 4,
    "government": 4,
    "financial_database": 3,
    "aggregator": 2,
    "market_data": 3,
    "vault": 2,
    "derived": 2,
    "unknown": 0,
}

# For these metrics a live MARKET feed is the correct authority, not a filing.
_MARKET_AUTHORITY_METRICS = {"price", "volume", "market_cap", "pe_ratio", "pb_ratio", "ps_ratio"}


@dataclass
class ConfidenceBreakdown:
    level: ConfidenceLevel
    source_quality: int
    freshness: str
    definition_clarity: bool
    cross_source_agreement: bool
    calculation_integrity: bool
    period_alignment: bool
    reasons: list[str]


def confidence_for(
    fact: FinancialFact,
    *,
    cross_source_agreement: bool = True,
    calculation_integrity: bool = True,
    period_alignment: Optional[bool] = None,
) -> ConfidenceBreakdown:
    """Compute a fact's confidence with the full breakdown, so a low score is explainable.

    `cross_source_agreement`, `calculation_integrity` and `period_alignment` come
    from the conflict / derived / period engines. When not supplied, period
    alignment is derived from the fact itself.
    """
    reasons: list[str] = []

    # Source quality — with the market-authority override for price-shaped facts.
    quality = SOURCE_QUALITY.get(fact.source_type, 0)
    if fact.metric in _MARKET_AUTHORITY_METRICS and fact.source_type == "market_data":
        quality = 5
    if quality == 0:
        reasons.append("source type is unknown")

    # Freshness. A fact that has never been classified carries the sentinel
    # UNVERIFIED; compute it rather than treating "not yet computed" as a state.
    state = fact.freshness
    if not state or state == fresh.UNVERIFIED:
        state = fresh.freshness_for(fact)

    # Definition clarity: an ambiguous or missing definition is a real weakness.
    definition_clarity = fact.definition is not None
    if not definition_clarity:
        reasons.append("metric definition is unresolved or ambiguous")

    # Period alignment: an explicit period with a type is required.
    period_ok = period_alignment
    if period_ok is None:
        period_ok = fact.period is not None and bool(fact.period.period_type)
    if not period_ok:
        reasons.append("period is missing or not comparable")

    # Hard failures cap confidence regardless of the other pillars.
    hard_fail = state in (fresh.SUPERSEDED,) or not cross_source_agreement

    level: ConfidenceLevel
    if hard_fail:
        level = "low"
        if state == fresh.SUPERSEDED:
            reasons.append("fact is superseded by a later revision")
        if not cross_source_agreement:
            reasons.append("independent sources disagree")
    elif not definition_clarity:
        # An unresolved accounting definition cannot be HIGH or MEDIUM — the
        # number may mean the wrong thing. This is the §4 guard at the confidence
        # layer, mirroring the definition gate.
        level = "low"
    elif quality >= 4 and state in (fresh.CURRENT, fresh.RECENT) and period_ok and calculation_integrity:
        level = "high"
    elif quality >= 3 and state in (fresh.CURRENT, fresh.RECENT, fresh.STALE) and period_ok:
        level = "medium"
    elif fact.source_type == "unknown" and fact.definition is None:
        level = "unverified"
        reasons.append("no usable source or definition")
    else:
        level = "low"

    return ConfidenceBreakdown(
        level=level,
        source_quality=quality,
        freshness=state,
        definition_clarity=definition_clarity,
        cross_source_agreement=cross_source_agreement,
        calculation_integrity=calculation_integrity,
        period_alignment=bool(period_ok),
        reasons=reasons,
    )


__all__ = ["SOURCE_QUALITY", "ConfidenceBreakdown", "confidence_for"]
