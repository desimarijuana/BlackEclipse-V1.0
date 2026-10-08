"""Health-aware source ordering for the retrieval planner (P0-2, ADR-H86).

The planner's per-data-type source order is a static policy. On its own it can
prefer a route that is recorded as failing over an equally-eligible route that is
recorded as healthy — the data is already reachable, but the selection ignores
the evidence. This module closes that gap WITHOUT making selection nondeterministic:

  * It reads the SAME `SourceHealth` ledger `get_source_health` reports (via the
    read-only bridge), so the planner and the operator see one truth.
  * It only ever REORDERS among sources the caller already made available; it
    never adds or removes a source. A route with no recorded runs is neutral.
  * It is fail-open: a missing bridge, an unavailable ledger, or malformed rows
    leave the static order untouched (health is best-effort, never load-bearing
    for correctness).

A route is keyed by (source × market × capability). A working quote says nothing
about a statement route, so the capability is derived from the data type and the
source — never blended.
"""

from __future__ import annotations

from typing import Any, Optional

from .planner import CRYPTO, SEC_FILINGS, STRUCTURED_LIVE, STRUCTURED_VAULT, WEB

# Data type → {planner source name: the bridge capability its health is recorded
# under}. A source absent here is not health-ranked for that data type.
_CAPABILITY_BY_DATATYPE: dict[str, dict[str, str]] = {
    "current_quote": {
        CRYPTO: "crypto_market_data",
        STRUCTURED_VAULT: "live_quote",
        STRUCTURED_LIVE: "live_quote",
    },
    "historical_prices": {STRUCTURED_VAULT: "price_history", STRUCTURED_LIVE: "price_history"},
    "company_profile": {STRUCTURED_VAULT: "fundamentals", STRUCTURED_LIVE: "fundamentals"},
    "financial_statements": {
        STRUCTURED_VAULT: "financial_statements",
        SEC_FILINGS: "sec_filings",
        STRUCTURED_LIVE: "financial_statements",
    },
    "macro_series": {STRUCTURED_VAULT: "macro_series", STRUCTURED_LIVE: "macro_series"},
    "derived_metric": {STRUCTURED_VAULT: "macro_series", STRUCTURED_LIVE: "macro_series"},
    "earnings": {STRUCTURED_VAULT: "financial_statements", WEB: "web_search"},
    "news": {WEB: "news"},
    "web_research": {WEB: "web_search"},
    "world_events": {WEB: "web_search"},
}

# Lower rank = preferred. Only a HEALTHY route is PROMOTED ahead of the rest;
# a degraded/failing route is not demoted below an *unobserved* route, because
# absence of evidence is not evidence of failure and moving a structured route
# behind generic web could invert precedence badly. A failing route therefore
# loses only to a healthy one — which is exactly the reported defect (a 100%-
# healthy route sitting unused next to a 0%-success route).
_RANK: dict[str, int] = {"healthy": 0, "unknown": 1, "degraded": 1, "failing": 1}

HealthIndex = dict[tuple[str, str, str], dict[str, int]]


def build_health_index(rows: Any) -> HealthIndex:
    """Fold `source_health` rows into `(source, capability, market) -> counts`.

    Counts are summed across asset classes for a market — "this source's success
    for this capability in this market" — because the planner selects a source,
    not an asset class. Rows are already canonicalised by the bridge (P1-5); a
    malformed row is skipped rather than trusted.
    """
    index: HealthIndex = {}
    if not isinstance(rows, list):
        return index
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        capability = str(row.get("capability") or "").strip()
        market = str(row.get("market") or "").strip()
        if not source or not capability or not market:
            continue
        try:
            success = max(0, int(row.get("success") or 0))
            fail = max(0, int(row.get("fail") or 0))
        except (TypeError, ValueError):
            continue
        key = (source, capability, market)
        cur = index.setdefault(key, {"success": 0, "fail": 0})
        cur["success"] += success
        cur["fail"] += fail
    return index


def _verdict(counts: Optional[dict[str, int]]) -> str:
    if counts is None:
        return "unknown"
    total = counts.get("success", 0) + counts.get("fail", 0)
    if total == 0:
        return "unknown"
    if counts.get("fail", 0) == 0:
        return "healthy"
    if counts.get("success", 0) == 0:
        return "failing"
    return "degraded"


def health_verdict(
    index: HealthIndex, source: str, capability: Optional[str], market: Optional[str]
) -> str:
    """The recorded verdict for one route, `unknown` when unobserved.

    An exact market match wins; a global (`*`) route is used when the market is
    not named or has no rows of its own.
    """
    if not capability:
        return "unknown"
    mkt = (market or "").strip()
    counts = index.get((source, capability, mkt))
    if counts is None:
        counts = index.get((source, capability, "*"))
    return _verdict(counts)


def rank_sources(
    order: list[str], index: Optional[HealthIndex], market: Optional[str], data_type: str
) -> tuple[list[str], list[str]]:
    """Reorder `order` so a healthy route outranks a degraded/failing one.

    Stable: sources in the same health class keep their static relative order, so
    the plan stays deterministic and explainable. Returns the reordered list and a
    human-readable note per source whose recorded verdict is not healthy.
    """
    if not index:
        return order, []

    capability_for = _CAPABILITY_BY_DATATYPE.get(data_type, {})
    if not capability_for:
        return order, []

    notes: list[str] = []
    ranked: list[tuple[int, int, str]] = []
    for position, name in enumerate(order):
        capability = capability_for.get(name)
        verdict = health_verdict(index, name, capability, market) if capability else "unknown"
        if capability and verdict in ("degraded", "failing"):
            notes.append(f"route {name} is recorded as {verdict} for {data_type} ({market or '*'})")
        ranked.append((_RANK.get(verdict, 1), position, name))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [name for _, _, name in ranked], notes


__all__ = ["build_health_index", "health_verdict", "rank_sources", "HealthIndex"]
