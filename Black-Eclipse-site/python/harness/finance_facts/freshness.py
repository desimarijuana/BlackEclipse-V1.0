"""Per-metric freshness engine (Universal Financial Data Accuracy, §14).

A price needs near-real-time; a filed annual statement stays valid until the next
one exists; shares outstanding must reflect recent corporate actions. There is NO
single universal threshold.

Freshness states: CURRENT / RECENT / STALE / VERY_STALE / SUPERSEDED /
CONFLICTING / UNVERIFIED.

The per-METRIC expected cadence is data (`METRIC_CADENCE_SECONDS`). A fact older
than its metric's cadence is stale; well beyond it, very stale. Freshness is
computed from the fact's OWN timestamps (source_timestamp preferred, then
publication_timestamp, then retrieved_timestamp) — never from the retrieval
clock dressed up as a market time.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from .model import FinancialFact

FreshnessState = str

CURRENT = "CURRENT"
RECENT = "RECENT"
STALE = "STALE"
VERY_STALE = "VERY_STALE"
SUPERSEDED = "SUPERSEDED"
CONFLICTING = "CONFLICTING"
UNVERIFIED = "UNVERIFIED"

# Expected time-to-live (seconds) per metric. `None` = open-ended (a reported
# historical figure does not expire on a wall clock; it is superseded, not aged).
HOUR = 3600
DAY = 24 * HOUR

METRIC_CADENCE_SECONDS: dict[str, Optional[int]] = {
    "price": 60,
    "volume": 60,
    "market_cap": 60,
    "shares_outstanding": 30 * DAY,     # changes on corporate actions
    "pe_ratio": DAY,
    "pb_ratio": DAY,
    # Reported statements: valid until a newer report exists → open-ended.
    "revenue": None,
    "net_income": None,
    "net_income_parent": None,
    "net_income_common": None,
    "eps": None,
    "gross_profit": None,
    "operating_income": None,
    "total_assets": None,
    "total_liabilities": None,
    "total_equity": None,
    "common_equity": None,
    "operating_cash_flow": None,
    "free_cash_flow": None,
}

# Default when a metric has no entry: treat like a reported fundamental (open).
_DEFAULT_CADENCE: Optional[int] = None

# Multiples of the cadence at which RECENT becomes STALE, and STALE VERY_STALE.
_RECENT_FACTOR = 1.0
_STALE_FACTOR = 8.0


def _age_seconds(iso: Optional[str], now: Optional[float]) -> Optional[float]:
    if not iso:
        return None
    text = str(iso).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    ref = _dt.datetime.now(_dt.timezone.utc) if now is None else _dt.datetime.fromtimestamp(now, _dt.timezone.utc)
    return (ref - parsed).total_seconds()


def fact_time(fact: FinancialFact) -> tuple[Optional[str], str]:
    """(timestamp, which) — the most authoritative time a fact carries.

    source_timestamp is the market time the value is about; publication is when it
    became known; retrieved is when we fetched it. We prefer the market time, then
    publication, then retrieval — and say which was used.
    """
    if fact.source_timestamp:
        return fact.source_timestamp, "source"
    if fact.publication_timestamp:
        return fact.publication_timestamp, "publication"
    if fact.retrieved_timestamp:
        return fact.retrieved_timestamp, "retrieved"
    return None, "none"


def freshness_for(
    fact: FinancialFact,
    *,
    now: Optional[float] = None,
    superseded: bool = False,
    conflicting: bool = False,
) -> FreshnessState:
    """Classify one fact's freshness, per its metric's cadence.

    SUPERSEDED and CONFLICTING are decided by OTHER engines (restatement /
    conflict) and passed in — freshness does not infer them from a value.
    """
    if superseded:
        return SUPERSEDED
    if conflicting:
        return CONFLICTING

    stamp, which = fact_time(fact)
    if stamp is None:
        return UNVERIFIED

    cadence = METRIC_CADENCE_SECONDS.get(fact.metric, _DEFAULT_CADENCE)
    if cadence is None:
        # Open-ended: a reported historical fact is current until superseded.
        return CURRENT

    age = _age_seconds(stamp, now)
    if age is None:
        return UNVERIFIED
    if age <= cadence * _RECENT_FACTOR:
        return CURRENT
    if age <= cadence * _STALE_FACTOR:
        return RECENT if age <= cadence * 2 else STALE
    return VERY_STALE


def is_usable(freshness: FreshnessState) -> bool:
    """A stale/very-stale fact may still be shown WITH its age; superseded and
    conflicting are never silently used as the current answer."""
    return freshness not in (SUPERSEDED,)


__all__ = [
    "CONFLICTING",
    "CURRENT",
    "METRIC_CADENCE_SECONDS",
    "RECENT",
    "STALE",
    "SUPERSEDED",
    "UNVERIFIED",
    "VERY_STALE",
    "fact_time",
    "freshness_for",
    "is_usable",
]
