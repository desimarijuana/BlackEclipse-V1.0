"""Task-aware source selection (Milestone 2C).

Deterministic and explainable: given a request, it returns an ordered list of
source names to try. It is NOT "always JDdS first" and NOT "always web first" —
the decision considers data type, required freshness, structured vs qualitative,
source reliability, availability and precision.

The selected strategy is stored in execution metadata by the layer, so a run can
be explained after the fact.

Rules (one row per data type; a new type gets a new row):
  * current_quote      → structured providers first (a precise number), web only
                         if the caller allows it and structured is unavailable.
  * historical_prices  → structured only. Web is FORBIDDEN here: a search engine
                         must never be asked to invent a precise series.
  * company_profile    → structured, then web for qualitative color.
  * financial_statements → structured first, then primary-source web.
  * earnings           → web/primary first (recent qualitative), structured supports.
  * macro_series       → structured only.
  * news / web_research → web first (qualitative + current).
  * world_events       → web (world-state feed).
  * derived_metric     → depends on the caller; structured only if it needs data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .contract import DataType, FinancialRetrievalRequest

# Provider names are opaque ids here; the layer maps them to source instances.
STRUCTURED_VAULT = "JDDS"
STRUCTURED_LIVE = "LIVE_STRUCTURED"
SEC_FILINGS = "SEC"
WEB = "WEB"


@dataclass
class RetrievalPlan:
    sources: list[str]
    rationale: str
    allow_web: bool = True
    requires_precise_data: bool = False
    warnings: list[str] = field(default_factory=list)


# Per-data-type source ordering. The FIRST available wins for a single-best
# retrieval; the layer may run the whole list for multi-source objectives.
#
# Source policy (deterministic, testable): official filing/company sources are
# preferred for reported financials, then the structured vault, then a reputable
# secondary. For `financial_statements` the order is:
#   1. SEC — issuer-filed XBRL (primary, US issuers)
#   2. JDDS — the structured vault (cached statements)
#   3. WEB — bounded primary-source web (last resort; facts must be span-verified)
# No data type makes every provider depend on one search call; SEC is a direct
# filing route, not a web search.
_PLAN: dict[str, list[str]] = {
    "current_quote": [STRUCTURED_VAULT, STRUCTURED_LIVE, WEB],
    "historical_prices": [STRUCTURED_VAULT, STRUCTURED_LIVE],
    "company_profile": [STRUCTURED_VAULT, STRUCTURED_LIVE, WEB],
    "financial_statements": [SEC_FILINGS, STRUCTURED_VAULT, WEB],
    "earnings": [WEB, STRUCTURED_VAULT],
    "macro_series": [STRUCTURED_VAULT, STRUCTURED_LIVE],
    "news": [WEB],
    "web_research": [WEB],
    "world_events": [WEB],
    "derived_metric": [STRUCTURED_VAULT, STRUCTURED_LIVE],
}

# Data types where a precise quantitative dataset is REQUIRED. If none is
# available, web research must not be used to invent the number.
_PRECISE: set[str] = {"historical_prices", "macro_series", "derived_metric", "current_quote"}

_RATIONALE: dict[str, str] = {
    "current_quote": "a precise latest price → structured provider; web is a last-resort fallback",
    "historical_prices": "a precise series is required → structured providers only",
    "company_profile": "profile metadata is structured; web supplies qualitative context",
    "financial_statements": "statements are reported facts → issuer filing (SEC) first, then the vault; primary-source web only as a last resort",
    "earnings": "earnings are recent and qualitative → web/primary first, statements support",
    "macro_series": "a precise historical series is required → structured only",
    "news": "current qualitative information → web research",
    "web_research": "qualitative research → web research",
    "world_events": "world-state events → web event feed",
    "derived_metric": "a calculation needs structured inputs → structured providers",
}


def plan_retrieval(
    request: FinancialRetrievalRequest,
    available_sources: Optional[set[str]] = None,
) -> RetrievalPlan:
    """Build an ordered, explainable plan for a request."""
    order = list(_PLAN.get(request.dataType, [WEB]))
    warnings: list[str] = []

    # A caller-supplied tier hint reorders preference (but never forces a source).
    if request.preferredSource:
        hint = request.preferredSource.upper()
        if hint in order:
            order = [hint] + [s for s in order if s != hint]

    # Web is forbidden when the caller says so, or when precise data is required
    # but web is not an acceptable substitute for it (it never is, for the
    # precise data types) — except current_quote, where a live web quote is a
    # legitimate *qualitative* clue but never labeled precise.
    precise = request.dataType in _PRECISE
    if not request.allowWeb:
        order = [s for s in order if s != WEB]
    if request.dataType in ("historical_prices", "macro_series", "derived_metric"):
        order = [s for s in order if s != WEB]

    # Availability filter (keeps the plan honest about what can actually run).
    if available_sources is not None:
        filtered = [s for s in order if s in available_sources]
        if not filtered and order:
            warnings.append(
                f"none of the planned sources {order} are available in this environment"
            )
        order = filtered

    if not order:
        warnings.append(f"no retrieval path is available for {request.dataType}")

    rationale = _RATIONALE.get(request.dataType, "no specific policy; web research")

    # Freshness influences the rationale (and the cache policy elsewhere).
    if request.freshnessRequirement in ("realtime", "intraday") and request.dataType == "current_quote":
        rationale += "; realtime freshness forbids stale cache"

    return RetrievalPlan(
        sources=order,
        rationale=rationale,
        allow_web=WEB in order,
        requires_precise_data=precise,
        warnings=warnings,
    )


__all__ = [
    "RetrievalPlan",
    "plan_retrieval",
    "STRUCTURED_VAULT",
    "STRUCTURED_LIVE",
    "SEC_FILINGS",
    "WEB",
]
