"""Task-aware source selection (Milestone 2C).

Deterministic and explainable: given a request, it returns an ordered list of
source names to try. It is NOT "always JDdS first" and NOT "always web first" —
the decision considers data type, required freshness, structured vs qualitative,
source reliability, availability and precision.

The ordering is no longer defined here. `retrieval/authority.py` owns the ONE
ordering table (`AUTHORITY`); this module adapts it into a `RetrievalPlan` and
applies the caller-facing rules (a tier hint, a web prohibition, declared MCP
sources, availability). One ordering in the tree, not three.

Rules (one row per data type lives in `authority.AUTHORITY`):
  * current_quote      → a live structured provider, then the vault, then web.
  * historical_prices  → structured only. Web is FORBIDDEN here: a search engine
                         must never be asked to invent a precise series.
  * company_profile    → structured, then web for qualitative color.
  * financial_statements → primary filing first, then the vault, then web.
  * earnings           → web/primary first (recent qualitative), structured supports.
  * macro_series       → structured only.
  * news / web_research → web first (qualitative + current).
  * world_events       → web (world-state feed).
  * derived_metric     → depends on the caller; structured only if it needs data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .authority import (
    SEC_FILINGS,
    STRUCTURED_LIVE,
    STRUCTURED_VAULT,
    WEB,
    authority_for,
)
from .contract import DataType, FinancialRetrievalRequest

# Re-exported so existing importers (`layer`, `health`, tests) keep working
# without knowing the table moved.


@dataclass
class RetrievalPlan:
    sources: list[str]
    rationale: str
    allow_web: bool = True
    requires_precise_data: bool = False
    warnings: list[str] = field(default_factory=list)


_RATIONALE: dict[str, str] = {
    "current_quote": "a precise latest price → structured providers (live then vault); web is a last-resort fallback",
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
    additional_sources: Optional[list[str]] = None,
) -> RetrievalPlan:
    """Build an ordered, explainable plan for a request.

    `additional_sources` are operator-declared MCP data-source names eligible for
    the requested data type (Milestone 6). They are considered AFTER the native
    structured sources but BEFORE generic web, so a declared data source can be
    selected when the vault is stale/missing without displacing a strong native
    provider. They are never forced: availability and freshness still decide.
    """
    authority = authority_for(request.dataType)
    order = list(authority.candidates)
    warnings: list[str] = []

    # A caller-supplied tier hint reorders preference (but never forces a source).
    if request.preferredSource:
        hint = request.preferredSource.upper()
        if hint in order:
            order = [hint] + [s for s in order if s != hint]

    # Web is forbidden when the caller says so, or when precise data is required
    # but web is not an acceptable substitute for it. The precise types
    # (historical_prices / macro_series / derived_metric) keep web forbidden even
    # if a table row were ever to list it.
    precise = authority.require_precise
    if not request.allowWeb:
        order = [s for s in order if s != WEB]
    if request.dataType in ("historical_prices", "macro_series", "derived_metric"):
        order = [s for s in order if s != WEB]

    # Insert operator-declared MCP data sources before generic web (never before
    # a strong structured provider). An MCP source is `secondary` tier, so it is
    # a legitimate substitute for web but not for the vault.
    if additional_sources:
        insert_at = order.index(WEB) if WEB in order else len(order)
        for extra in additional_sources:
            if extra not in order:
                order.insert(insert_at, extra)

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
