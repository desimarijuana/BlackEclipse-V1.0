"""Freshness + reliability policies (shared by the cache and the planner).

Different data changes at different rates. These policies are data, not branches
scattered through the code, so a new data type gets one row.
"""

from __future__ import annotations

from typing import Optional

from .contract import DataType, FreshnessRequirement, SourceTier

# Default freshness requirement per data type when the caller does not state one.
DEFAULT_FRESHNESS: dict[str, FreshnessRequirement] = {
    "current_quote": "realtime",
    "historical_prices": "slow",
    "company_profile": "slow",
    "financial_statements": "slow",
    "earnings": "daily",
    "macro_series": "slow",
    "news": "intraday",
    "web_research": "daily",
    "world_events": "intraday",
    "derived_metric": "any",
}

# Cache TTL (seconds) per data type. `realtime`/`intraday` are intentionally
# short so we never present a stale quote as current.
CACHE_TTL_SECONDS: dict[str, int] = {
    "current_quote": 60,
    "historical_prices": 6 * 60 * 60,
    "company_profile": 24 * 60 * 60,
    "financial_statements": 24 * 60 * 60,
    "earnings": 60 * 60,
    "macro_series": 12 * 60 * 60,
    "news": 10 * 60,
    "web_research": 30 * 60,
    "world_events": 10 * 60,
    "derived_metric": 6 * 60 * 60,
}

# Freshness requirement → allowed staleness (seconds) before data is "stale".
FRESHNESS_MAX_AGE_SECONDS: dict[str, int] = {
    "realtime": 60,
    "intraday": 15 * 60,
    "daily": 24 * 60 * 60,
    "slow": 7 * 24 * 60 * 60,
    "any": 10 * 365 * 24 * 60 * 60,
}

# Natural PUBLISHING cadence per data type, when a source does not declare its
# own. Some data is periodic by nature: a `financial_statements` leg's newest
# observation is the last FY/quarter END, so a currently-valid annual filing is
# always ~1 year "old" by wall-clock. Comparing that against a 7-day freshness
# window would flag every legitimate filing stale (Issue 4). The cadence lets the
# validator treat a within-cadence figure as DELAYED-by-design, not stale, while
# keeping strict windows for prices/quotes (which have no cadence entry here).
DEFAULT_CADENCE_SECONDS: dict[str, int] = {
    "financial_statements": 400 * 24 * 60 * 60,  # ~annual reporting + filing lag
    "earnings": 95 * 24 * 60 * 60,               # ~quarterly
    "macro_series": 45 * 24 * 60 * 60,           # monthly releases + revision lag
}


def freshness_for(data_type: str, requested: Optional[str] = None) -> FreshnessRequirement:
    if requested:
        return requested  # type: ignore[return-value]
    return DEFAULT_FRESHNESS.get(data_type, "any")


def cadence_for(data_type: str) -> Optional[int]:
    """The natural publishing cadence for a data type, or None (not periodic)."""
    return DEFAULT_CADENCE_SECONDS.get(data_type)


def ttl_seconds(data_type: str) -> int:
    return CACHE_TTL_SECONDS.get(data_type, 15 * 60)


def max_age_seconds(freshness: str) -> int:
    return FRESHNESS_MAX_AGE_SECONDS.get(freshness, FRESHNESS_MAX_AGE_SECONDS["any"])


# Trust ranking for conflict resolution (higher wins when timestamps tie).
TIER_RANK: dict[str, int] = {
    "primary": 7,
    "official": 6,
    "derived": 5,
    "structured": 4,
    "secondary": 3,
    "cache": 2,
    "unknown": 1,
}


def tier_rank(tier: str) -> int:
    return TIER_RANK.get(tier, 0)


__all__ = [
    "DEFAULT_FRESHNESS",
    "CACHE_TTL_SECONDS",
    "FRESHNESS_MAX_AGE_SECONDS",
    "DEFAULT_CADENCE_SECONDS",
    "TIER_RANK",
    "freshness_for",
    "cadence_for",
    "ttl_seconds",
    "max_age_seconds",
    "tier_rank",
]
