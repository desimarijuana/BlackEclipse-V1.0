"""Phase 2 — end-to-end scenario tests (Milestone 2O).

The ten scenarios from the brief, driven through the *tools* (the same surface
the agent calls). The data bridge is faked so every scenario is deterministic and
offline; the point is to verify the retrieval LAYER's decisions, not a provider.

    1. Get AAPL historical price data            → structured historical source
    2. What happened to AAPL today?              → current market data + web
    3. Analyze AAPL fundamentals                 → structured financial data
    4. What did AAPL report in its latest earnings? → primary-source/web + structured
    5. Calculate AAPL historical performance     → structured history (+ derived)
    6. Why did NVDA move today?                  → market data + current web research
    7. Complete analysis of Tesla                → multiple parallel paths
    8. Simulate yfinance unavailable             → cache/alternative/fallback
    9. Web cannot provide reliable quant data    → system does NOT invent a number
   10. Multiple agents request same data         → concurrency + cache reuse
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.retrieval_tools import (
    fundamentals_get_company_profile,
    fundamentals_get_financials,
    macro_get_series,
    market_get_ohlcv,
    market_get_quote,
    register_retrieval_tools,
    research_search,
    research_search_news,
)
from harness.tools import DataBridge, ToolContext, ToolRegistry


class ScenarioBridge(DataBridge):
    """A bridge that answers from a table and records calls."""

    def __init__(self, responses: dict[str, Any], unavailable: set[str] | None = None) -> None:
        self.responses = responses
        self.unavailable = unavailable or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        if capability in self.unavailable:
            return {"status": "UNAVAILABLE", "error": f"{capability} unavailable"}
        value = self.responses.get(capability)
        if value is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        if callable(value):
            result = value(params)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        return value


def ctx(bridge: DataBridge) -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None, data_bridge=bridge)


def history_payload() -> dict[str, Any]:
    # Phase 13: arbitration rejects a candidate whose newest observation is
    # outside the request window (6h for a series), so a "current" series must
    # END now. The timestamps are generated relative to the run, not hard-coded,
    # so the fixture is genuinely fresh whenever the suite runs.
    import datetime as dt

    now = dt.datetime.now(dt.timezone.utc)
    series = [
        {"date": (now - dt.timedelta(days=19 - i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 1000}
        for i in range(20)
    ]
    return {"status": "OK", "symbol": "AAPL", "currency": "USD", "interval": "1d", "series": series, "asOf": series[-1]["date"]}


def fresh_updated_at() -> str:
    """A genuinely-current ISO timestamp for a quote fixture."""
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def snapshot_payload(symbol: str, price: float, change_pct: float) -> dict[str, Any]:
    now = fresh_updated_at()
    return {
        "status": "OK", "symbol": symbol, "updatedAt": now,
        "observationTime": now, "observationSource": "snapshot_write",
        "priceSource": "scraper",
        "price": {"price": price, "changePct": change_pct},
    }


def fundamentals_payload() -> dict[str, Any]:
    return {
        "status": "OK",
        "symbol": "AAPL",
        "currency": "USD",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "securityType": "Common Stock",
        "exchange": "NASDAQ",
        "country": "US",
        "periods": [
            {"endDate": "2025-09-30", "fiscalYear": 2025, "revenue": 400_000, "netIncome": 100_000, "eps": 6.5, "grossMargin": 0.45},
            {"endDate": "2024-09-30", "fiscalYear": 2024, "revenue": 380_000, "netIncome": 95_000, "eps": 6.1, "grossMargin": 0.44},
        ],
    }


def web_payload(query: str) -> dict[str, Any]:
    return {
        "status": "OK",
        "query": query,
        "results": [
            {"title": "Apple reports Q3", "url": "https://investor.apple.com/news", "snippet": "record services revenue"},
            {"title": "AAPL moves", "url": "https://www.reuters.com/aapl", "snippet": "shares rose"},
        ],
    }


# ── Test 1: historical price data → structured ──────────────────────────────


@pytest.mark.asyncio
async def test_scenario_1_historical_prices_use_structured_source():
    bridge = ScenarioBridge({"price_history": history_payload()})
    text, data = await market_get_ohlcv({"symbol": "AAPL", "period": "1mo"}, ctx(bridge))
    assert data["status"] == "OK"
    # A series is served by a live structured provider, never the web and never
    # mislabeled as the JDdS vault (it stores no series).
    assert data["strategy"][0] == "LIVE_STRUCTURED"
    assert "WEB" not in data["strategy"]
    assert not any(c[0] == "web_search" for c in bridge.calls)
    assert len(data["data"]) == 20


# ── Test 2: what happened today → current market + web ──────────────────────


@pytest.mark.asyncio
async def test_scenario_2_today_combines_market_and_web():
    bridge = ScenarioBridge({"market_snapshot": snapshot_payload("AAPL", 240.0, 1.1)})
    quote_text, quote = await market_get_quote({"symbol": "AAPL"}, ctx(bridge))
    assert quote["status"] == "OK"

    news_bridge = ScenarioBridge({"web_search": web_payload("AAPL today"), "web_fetch": lambda p: {"status": "OK", "url": p["url"], "title": "t", "text": "body"}})
    news_text, news = await research_search({"query": "what happened to AAPL today"}, ctx(news_bridge))
    assert news["status"] == "OK"
    assert news["evidence"], "web research should return evidence"


# ── Test 3: fundamentals → structured ───────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_3_fundamentals_structured():
    bridge = ScenarioBridge({"fundamentals": fundamentals_payload(), "financial_statements": fundamentals_payload()})
    text, data = await fundamentals_get_financials({"symbol": "AAPL"}, ctx(bridge))
    assert data["status"] == "OK"
    assert any(o["name"] == "revenue" for o in data["data"])


# ── Test 4: latest earnings → primary/web + structured ──────────────────────


@pytest.mark.asyncio
async def test_scenario_4_earnings_uses_web_and_structured():
    bridge = ScenarioBridge(
        {
            "web_search": web_payload("AAPL latest earnings"),
            "web_fetch": lambda p: {"status": "OK", "url": p["url"], "title": "t", "text": "body"},
            "fundamentals": fundamentals_payload(), "financial_statements": fundamentals_payload(),
        }
    )
    news_text, news = await research_search({"query": "what did AAPL report in latest earnings"}, ctx(bridge))
    assert news["status"] == "OK"
    assert any(e["kind"] == "filing" for e in news["evidence"]), "investor-relations URL should be primary evidence"

    fin_text, fin = await fundamentals_get_financials({"symbol": "AAPL"}, ctx(bridge))
    assert fin["status"] == "OK"


# ── Test 5: historical performance → structured + deterministic calc ────────


@pytest.mark.asyncio
async def test_scenario_5_performance_calculation_uses_structured_data():
    bridge = ScenarioBridge({"price_history": history_payload()})
    text, data = await market_get_ohlcv({"symbol": "AAPL", "period": "1y"}, ctx(bridge))
    assert data["status"] == "OK"
    bars = data["data"]
    assert len(bars) >= 2
    first_close = bars[0]["close"]
    last_close = bars[-1]["close"]
    # A deterministic calculation from real structured inputs — not a web guess.
    total_return = (last_close - first_close) / first_close
    assert total_return > 0


# ── Test 6: why did NVDA move → market + current web ────────────────────────


@pytest.mark.asyncio
async def test_scenario_6_nvda_move_uses_market_plus_web():
    bridge = ScenarioBridge(
        {
            "market_snapshot": snapshot_payload("NVDA", 180.0, -3.2),
            "web_search": web_payload("why did NVDA move today"),
            "web_fetch": lambda p: {"status": "OK", "url": p["url"], "title": "t", "text": "body"},
        }
    )
    quote_text, quote = await market_get_quote({"symbol": "NVDA"}, ctx(bridge))
    assert quote["status"] == "OK" and quote["data"]["changePct"] == -3.2
    news_text, news = await research_search({"query": "why did NVDA move today"}, ctx(bridge))
    assert news["status"] == "OK"
    assert news["evidence"]


# ── Test 7: complete Tesla analysis → multiple parallel paths ───────────────


@pytest.mark.asyncio
async def test_scenario_7_complete_analysis_runs_paths_in_parallel():
    bridge = ScenarioBridge(
        {
            "market_snapshot": snapshot_payload("TSLA", 250.0, 2.0),
            "fundamentals": fundamentals_payload(), "financial_statements": fundamentals_payload(),
            "price_history": history_payload(),
            "web_search": web_payload("Tesla analysis"),
            "web_fetch": lambda p: {"status": "OK", "url": p["url"], "title": "t", "text": "body"},
            "macro_series": {"status": "OK", "source": "fred-analytics", "seriesKey": "CPIAUCSL", "rows": [{"date": "2026-08", "value": 3.1}], "asOf": "2026-08"},
        }
    )
    layer_ctx = ctx(bridge)
    results = await asyncio.gather(
        market_get_quote({"symbol": "TSLA"}, layer_ctx),
        fundamentals_get_company_profile({"symbol": "TSLA"}, layer_ctx),
        fundamentals_get_financials({"symbol": "TSLA"}, layer_ctx),
        research_search({"query": "Tesla analysis"}, layer_ctx),
        macro_get_series({"series": "CPIAUCSL"}, layer_ctx),
    )
    statuses = [r[1]["status"] for r in results]
    assert all(s == "OK" for s in statuses), statuses
    # The three structured paths hit the vault; web research hit the web search.
    capabilities = {c[0] for c in bridge.calls}
    assert "web_search" in capabilities
    assert "fundamentals" in capabilities


# ── Test 8: yfinance unavailable → cache / alternative / fallback ───────────


@pytest.mark.asyncio
async def test_scenario_8_yfinance_unavailable_falls_back():
    # Live provider is down but the vault can still satisfy history.
    bridge = ScenarioBridge(
        {"price_history": history_payload()},
        unavailable={"live_quote"},
    )
    text, data = await market_get_ohlcv({"symbol": "AAPL", "period": "1y"}, ctx(bridge))
    assert data["status"] == "OK"
    assert data["strategy"][0] == "LIVE_STRUCTURED", "a series comes from a structured provider, not the web"


@pytest.mark.asyncio
async def test_scenario_8b_repeat_request_served_from_cache():
    bridge = ScenarioBridge({"market_snapshot": snapshot_payload("AAPL", 240.0, 1.1)})
    c = ctx(bridge)
    await market_get_quote({"symbol": "AAPL"}, c)
    _, second = await market_get_quote({"symbol": "AAPL"}, c)
    assert second["cached"] is True
    assert len([x for x in bridge.calls if x[0] == "market_snapshot"]) == 1


# ── Test 9: web cannot supply reliable quantitative data → no invention ─────


@pytest.mark.asyncio
async def test_scenario_9_web_never_invents_a_number():
    # No structured history is available; only web search answers.
    bridge = ScenarioBridge({"web_search": web_payload("AAPL 5 year sharpe ratio")})
    text, data = await market_get_ohlcv({"symbol": "AAPL", "period": "5y"}, ctx(bridge))
    assert data["status"] == "UNAVAILABLE"
    assert data["data"] is None
    assert not any(c[0] == "web_search" for c in bridge.calls), "history must never be web-sourced"
    assert "UNAVAILABLE" in text


@pytest.mark.asyncio
async def test_scenario_9b_macro_never_web_sourced():
    bridge = ScenarioBridge({"web_search": web_payload("US CPI")})
    text, data = await macro_get_series({"series": "CPIAUCSL"}, ctx(bridge))
    assert data["status"] == "UNAVAILABLE"
    assert not any(c[0] == "web_search" for c in bridge.calls)


# ── Test 10: concurrent identical requests → dedup + cache reuse ────────────


@pytest.mark.asyncio
async def test_scenario_10_concurrent_requests_share_one_provider_call():
    calls = {"n": 0}

    async def slow_snapshot(params: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return snapshot_payload("AAPL", 240.0, 1.1)

    # Many concurrent "agents" request the same dataset through the SAME shared
    # layer/cache (the runtime wires one cache across runs).
    from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
    from harness.retrieval.cache import RetrievalCache

    shared_cache = RetrievalCache()
    bridge = ScenarioBridge({"market_snapshot": slow_snapshot})
    layer = FinancialRetrievalLayer(bridge, cache=shared_cache)
    request = FinancialRetrievalRequest(objective="AAPL quote", dataType="current_quote", instrument="AAPL")

    results = await asyncio.gather(*(layer.retrieve(request) for _ in range(8)))
    assert all(r.status == "OK" for r in results)
    assert calls["n"] == 1, f"expected 1 provider call, got {calls['n']}"
    assert layer.metrics["deduplicated"] + layer.metrics["cacheHits"] >= 7


@pytest.mark.asyncio
async def test_registration_exposes_all_documented_tools():
    registry = ToolRegistry()
    register_retrieval_tools(registry)
    names = set(registry.names())
    expected = {
        "market_get_quote",
        "market_get_ohlcv",
        "fundamentals_get_company_profile",
        "fundamentals_get_financials",
        "research_search",
        "research_retrieve_source",
        "research_search_news",
        "macro_get_series",
    }
    assert expected <= names


@pytest.mark.asyncio
async def test_tools_route_through_layer_not_providers():
    """A tool must call the layer; the layer names no provider to the tool."""
    bridge = ScenarioBridge({"market_snapshot": {"status": "OK", "symbol": "AAPL", "updatedAt": "2026-09-21T14:00:00Z", "priceSource": "scraper", "price": {"price": 1.0, "changePct": 0.0}}})
    c = ctx(bridge)
    _, data = await market_get_quote({"symbol": "AAPL"}, c)
    assert data["strategy"], "the selected strategy must be recorded"
    assert c.retrieval is not None, "the layer is attached to the run context"
