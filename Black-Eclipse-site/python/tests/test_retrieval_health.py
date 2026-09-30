"""P0-2 — health-aware retrieval planning (ADR-H86).

The planner's static order can prefer a route recorded as failing over an
equally-eligible healthy one. These tests pin that the layer reads the SAME
`source_health` ledger the operator sees, reorders only among already-available
sources, stays deterministic for equal health, and fails open.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
from harness.retrieval.health import build_health_index, health_verdict, rank_sources
from harness.tools import DataBridge


class FakeBridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        value = self.responses.get(capability)
        if value is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        result = value(params) if callable(value) else value
        if asyncio.iscoroutine(result):
            result = await result
        return result


def quote_payload(provider: str = "scraper") -> dict[str, Any]:
    return {
        "status": "OK",
        "symbol": "AAPL",
        "provider": provider,
        "updatedAt": "2026-09-20T12:00:00.000Z",
        "price": {"price": 100.0, "changePct": 1.0, "volume": 1, "marketCap": None},
    }


HEALTH_ROWS = [
    {"source": "LIVE_STRUCTURED", "capability": "live_quote", "market": "US", "success": 38, "fail": 0},
    {"source": "JDDS", "capability": "live_quote", "market": "US", "success": 0, "fail": 8},
]


# ── pure index / verdict / ranking ──────────────────────────────────────────


def test_build_health_index_sums_across_asset_classes():
    index = build_health_index(
        [
            {"source": "yfinance", "capability": "live_quote", "market": "US", "success": 2, "fail": 0},
            {"source": "yfinance", "capability": "live_quote", "market": "US", "success": 3, "fail": 1},
            {"source": "WEB", "capability": "web_search", "market": "*", "success": 1, "fail": 0},
        ]
    )
    assert index[("yfinance", "live_quote", "US")] == {"success": 5, "fail": 1}
    assert index[("WEB", "web_search", "*")] == {"success": 1, "fail": 0}


def test_build_health_index_skips_malformed_rows():
    index = build_health_index([{"source": "", "capability": "x", "market": "US"}, "nope", 7])
    assert index == {}


def test_health_verdict_falls_back_to_global_and_reports_unknown():
    index = build_health_index(
        [{"source": "WEB", "capability": "web_search", "market": "*", "success": 0, "fail": 3}]
    )
    # No PK-specific row → the global (`*`) route is used.
    assert health_verdict(index, "WEB", "web_search", "PK") == "failing"
    # No capability → never guesses.
    assert health_verdict(index, "WEB", None, "PK") == "unknown"


def test_rank_moves_healthy_above_failing_and_is_stable():
    index = build_health_index(HEALTH_ROWS)
    order, notes = rank_sources(["JDDS", "LIVE_STRUCTURED", "WEB"], index, "US", "current_quote")
    assert order[0] == "LIVE_STRUCTURED"
    assert order.index("JDDS") < order.index("WEB")  # WEB is unobserved, so it does not leap JDDS
    assert any("JDDS" in n and "failing" in n for n in notes)
    # Equal-health sources keep their static relative order.
    order2, _ = rank_sources(["JDDS", "LIVE_STRUCTURED"], build_health_index([]), "US", "current_quote")
    assert order2 == ["JDDS", "LIVE_STRUCTURED"]


def test_a_failing_route_is_not_demoted_below_an_unobserved_one():
    # JDDS failing, WEB unobserved → WEB may pass JDDS, but a structured route
    # must never be pushed behind web merely for lacking runs.
    index = build_health_index(
        [{"source": "JDDS", "capability": "live_quote", "market": "US", "success": 0, "fail": 5}]
    )
    order, _ = rank_sources(["JDDS", "WEB"], index, "US", "current_quote")
    # Neither is healthy, so the static precedence is preserved.
    assert order == ["JDDS", "WEB"]


# ── layer integration ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_layer_reorders_around_a_failing_route():
    bridge = FakeBridge(
        {
            "source_health": {"status": "OK", "rows": HEALTH_ROWS},
            "market_snapshot": quote_payload("scraper"),
            "live_quote": quote_payload("yfinance"),
        }
    )
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL", market="US")
    )
    # The healthy live route is tried before the failing vault route.
    assert result.strategy[0] == "LIVE_STRUCTURED"
    assert any("JDDS" in w and "failing" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_layer_static_order_when_no_health_is_available():
    bridge = FakeBridge({"market_snapshot": quote_payload(), "live_quote": quote_payload()})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL", market="US")
    )
    # Fail-open: with no ledger, the static plan (vault first) is unchanged.
    assert result.strategy[0] == "JDDS"


@pytest.mark.asyncio
async def test_health_is_fetched_at_most_once():
    bridge = FakeBridge(
        {
            "source_health": {"status": "OK", "rows": HEALTH_ROWS},
            "market_snapshot": quote_payload(),
            "live_quote": quote_payload("yfinance"),
        }
    )
    layer = FinancialRetrievalLayer(bridge)
    await layer.retrieve(FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL", market="US"))
    await layer.retrieve(FinancialRetrievalRequest(objective="q2", dataType="current_quote", instrument="MSFT", market="US"))
    assert len([c for c in bridge.calls if c[0] == "source_health"]) == 1
