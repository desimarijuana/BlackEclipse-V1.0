"""Market Data Gateway tests — routing, fallback, normalization, quality,
conflicts, freshness and failure handling. All provider calls go through a fake
bridge; no network.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.market.cache import MarketCache
from harness.market.gateway import MarketDataGateway
from harness.market.router import ProviderRouter
from harness.market.tools import register_market_tools
from harness.tools import DataBridge, ToolContext, ToolRegistry


class FakeBridge(DataBridge):
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        if capability == "market_snapshot":
            symbol = params.get("symbol", "AAPL")
            market = params.get("market") or "US"
            if symbol in ("BAD", ""):
                return {"status": "UNAVAILABLE", "failureClass": "not_found", "error": f"{symbol} not found"}
            is_crypto = "-" in symbol or market == "CRYPTO"
            return {
                "status": "OK", "symbol": symbol, "market": market,
                "exchange": "BINANCE" if is_crypto else "NASDAQ",
                "currency": "USD",
                "assetClass": "crypto" if is_crypto else "equity",
                "instrumentId": f"{market}:{symbol}",
            }
        if capability == "market_data":
            value = self.responses.get(params.get("capability"))
            if value is None:
                return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "no fake"}
            if callable(value):
                return value(params)
            return value
        return {"status": "UNAVAILABLE", "error": "unknown capability"}


def quote_payload(price: float = 237.42, provider: str = "yahoo") -> dict[str, Any]:
    import time as _t

    now = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime()) + "Z"
    return {
        "status": "OK", "provider": provider, "symbol": "AAPL",
        "price": {"price": price, "changePct": 1.2, "previousClose": 235.0, "volume": 1000},
        "asOf": now, "observationTime": now,
        "observationSource": "provider_asof",
    }


def gateway(responses: dict[str, Any]) -> tuple[MarketDataGateway, FakeBridge]:
    bridge = FakeBridge(responses)
    gw = MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())
    return gw, bridge


def test_get_quote_normalizes():
    gw, bridge = gateway({"quote": quote_payload()})
    result = asyncio.run(gw.get_quote("AAPL", "US"))
    assert result.price == 237.42
    assert result.meta.provider == "yahoo"
    assert result.meta.data_type == "quote"
    assert any(c[0] == "market_snapshot" for c in bridge.calls)
    assert any(c[0] == "market_data" for c in bridge.calls)


def test_get_quote_symbol_not_found():
    gw, _ = gateway({})
    result = asyncio.run(gw.get_quote("BAD", "US"))
    assert result.__class__.__name__ == "MarketError"
    assert result.code == "SYMBOL_NOT_FOUND"


def test_fallback_to_second_provider():
    responses = {
        "quote": {
            "status": "UNAVAILABLE", "failureClass": "source_failure", "error": "yahoo down",
            "provider": "yahoo",
        }
    }

    def per_provider(params: dict[str, Any]) -> dict[str, Any]:
        if params.get("provider") == "binance":
            return quote_payload(provider="binance")
        return {"status": "UNAVAILABLE", "failureClass": "source_failure", "error": "yahoo down"}

    bridge = FakeBridge({"quote": per_provider})
    # Equity asset class: binance is not eligible, so instead use crypto.
    bridge_inst = MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())
    # Force a crypto symbol so both yahoo and binance are candidates.
    result = asyncio.run(bridge_inst.get_quote("BTC-USD", "CRYPTO"))
    assert result.price == 237.42
    assert result.meta.provider == "binance"


def test_historical_series_normalized():
    payload = {
        "status": "OK", "provider": "yahoo", "symbol": "AAPL", "interval": "1d",
        "series": [
            {"timestamp": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"timestamp": "2026-01-02", "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 20},
        ],
        "asOf": "2026-01-02",
    }
    gw, _ = gateway({"historical": payload})
    result = asyncio.run(gw.get_historical_prices("AAPL", "US"))
    assert len(result.bars) == 2
    assert result.bars[0].close == 1.5
    assert result.meta.quality in ("valid", "warning")


def test_orderbook_routes_to_keyed_provider_for_equity():
    # Equity order books are served by keyed providers (Polygon/Finnhub). With no
    # provider data the result is an honest no-data error, NOT a blanket refusal.
    gw, _ = gateway({})
    result = asyncio.run(gw.get_orderbook("AAPL", "US"))
    assert result.__class__.__name__ == "MarketError"
    assert result.code == "DATA_NOT_AVAILABLE"

    # With a top-of-book (NBBO) payload it succeeds and names the provider.
    payload = {
        "status": "OK", "provider": "polygon", "symbol": "AAPL",
        "bids": [[189.5, 100]], "asks": [[189.55, 80]],
        "bestBid": 189.5, "bestAsk": 189.55,
        "observationTime": "2026-10-07T00:00:00Z", "observationSource": "provider_asof",
    }
    gw2, _ = gateway({"orderbook": payload})
    result2 = asyncio.run(gw2.get_orderbook("AAPL", "US"))
    assert result2.meta.provider == "polygon"
    assert result2.best_bid == 189.5


def test_supply_unsupported_for_equity():
    gw, _ = gateway({})
    result = asyncio.run(gw.get_supply("AAPL", "US"))
    assert result.code == "UNSUPPORTED_CAPABILITY"


def test_quality_withholds_invalid_quote():
    bad = quote_payload(price=-1.0)
    gw, _ = gateway({"quote": bad})
    result = asyncio.run(gw.get_quote("AAPL", "US"))
    # An invalid value is withheld as a MarketError, never returned clean.
    assert result.__class__.__name__ == "MarketError"


def test_cache_hit_avoids_second_provider_call():
    gw, bridge = gateway({"quote": quote_payload()})
    asyncio.run(gw.get_quote("AAPL", "US"))
    calls_after_first = len(bridge.calls)
    asyncio.run(gw.get_quote("AAPL", "US"))
    # The second call is served from cache; no new provider call.
    assert len(bridge.calls) == calls_after_first
    assert gw.metrics["cacheHits"] >= 1


def test_tools_registered_and_invocable():
    registry = ToolRegistry()
    register_market_tools(registry)
    assert registry.get("get_quote") is not None
    assert registry.get("stream_market_data") is not None

    from harness.tools import ToolContext

    ctx = ToolContext(run_id="r1", log=lambda *a, **k: None,
                      data_bridge=FakeBridge({"quote": quote_payload()}))
    result = asyncio.run(
        registry.execute("get_quote", "c1", {"symbol": "AAPL", "market": "US"}, ctx)
    )
    assert result.ok
    assert "quote" in result.text.lower() or "AAPL" in result.text
    assert result.data.get("status") == "OK"


def test_all_fourteen_tools_invocable_through_registry():
    """Every requested market tool can be invoked through the real registry.

    A bridge that answers every capability lets each tool run its routing,
    normalization and quality path end-to-end (no network).
    """

    def any_capability(params: dict[str, Any]) -> dict[str, Any]:
        cap = params.get("capability")
        now = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())
        base = {"status": "OK", "provider": "yahoo", "symbol": params.get("symbol"),
                "observationTime": now, "observationSource": "provider_asof"}
        if cap == "historical":
            base["series"] = [{"timestamp": "2026-01-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},
                              {"timestamp": "2026-01-02", "open": 1.5, "high": 2, "low": 1, "close": 2, "volume": 20}]
        elif cap == "orderbook":
            base.update(bids=[[100, 1]], asks=[[101, 1]], bestBid=100, bestAsk=101)
        elif cap == "trades":
            base["trades"] = [{"id": 1, "timestamp": now, "price": 100, "quantity": 1, "side": "buy"}]
        elif cap == "options":
            base.update(expirations=["2026-06-19"], underlyingPrice=100,
                        contracts=[{"expiration": "2026-06-19", "strike": 100, "type": "call",
                                    "bid": 1, "ask": 1.1, "impliedVolatility": 0.3}])
        elif cap == "quote":
            base["price"] = {"price": 100.0, "changePct": 1.0, "marketCap": 1_000_000}
        elif cap == "market_cap":
            base.update(marketCap=1_000_000, price=100.0, sharesOutstanding=10_000)
        elif cap == "fx":
            base.update(mid=1.08, rate=1.08)
        elif cap == "supply":
            base.update(circulatingSupply=19_000_000, totalSupply=21_000_000)
        elif cap == "funding":
            base.update(fundingRate=0.0001, fundingIntervalHours=8)
        elif cap == "open_interest":
            base.update(openInterest=1000, openInterestUsd=50_000_000)
        elif cap == "bonds":
            base["yield"] = 4.2
        return base

    registry = ToolRegistry()
    register_market_tools(registry)
    bridge = FakeBridge({"historical": any_capability, "ohlcv": any_capability,
                         "quote": any_capability, "volume": any_capability,
                         "orderbook": any_capability, "trades": any_capability,
                         "market_cap": any_capability, "supply": any_capability,
                         "funding": any_capability, "open_interest": any_capability,
                         "options": any_capability, "fx": any_capability, "bonds": any_capability})
    ctx = ToolContext(run_id="r2", log=lambda *a, **k: None, data_bridge=bridge)

    invocations = {
        "get_quote": {"symbol": "AAPL", "market": "US"},
        "get_historical_prices": {"symbol": "AAPL", "market": "US", "period": "1y"},
        "get_ohlcv": {"symbol": "AAPL", "market": "US", "interval": "1d"},
        "get_volume": {"symbol": "AAPL", "market": "US"},
        "get_orderbook": {"symbol": "BTC-USD", "market": "CRYPTO"},
        "get_trades": {"symbol": "BTC-USD", "market": "CRYPTO"},
        "get_market_cap": {"symbol": "AAPL", "market": "US"},
        "get_supply": {"symbol": "BTC-USD", "market": "CRYPTO"},
        "get_funding_rate": {"symbol": "BTC-USD", "market": "CRYPTO"},
        "get_open_interest": {"symbol": "BTC-USD", "market": "CRYPTO"},
        "get_options_chain": {"symbol": "AAPL", "market": "US"},
        "get_fx_rate": {"symbol": "EURUSD=X", "market": "FX"},
        "get_bond_data": {"symbol": "US10Y", "market": "US"},
    }
    for name, args in invocations.items():
        result = asyncio.run(registry.execute(name, f"c-{name}", args, ctx))
        assert result.ok, f"{name} failed: {result.text}"
        assert result.data.get("status") == "OK", f"{name} -> {result.data.get('status')}"
    # stream_market_data returns OK/unavailable honestly even without transport.
    stream = asyncio.run(
        registry.execute("stream_market_data", "c-stream",
                         {"action": "snapshot"}, ctx)
    )
    assert stream.ok
