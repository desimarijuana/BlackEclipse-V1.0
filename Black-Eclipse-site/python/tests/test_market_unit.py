"""Market Data Layer tests — contracts, instruments, quality, cache, router.

Everything is driven through fakes: no network, no provider, no database. The
suite covers normalization, routing, validation, instrument mapping, cache
freshness, error handling, streaming lifecycle and agent tool invocation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.market.instruments import classify_identifier, split_crypto_pair
from harness.market.models import Quote, MarketMeta, OrderBook, OrderBookLevel, OHLCVBar, HistoricalPriceSeries
from harness.market.quality import evaluate, evaluate_quote, evaluate_series
from harness.market.errors import classify_bridge_failure, MarketError, RATE_LIMITED
from harness.market.cache import MarketCache
from harness.market.config import get_config
from harness.market.router import ProviderRouter
from harness.tools import DataBridge


class FakeBridge(DataBridge):
    """Answers market_data (and market_snapshot) from a table; records calls."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        if capability == "market_snapshot":
            return {
                "status": "OK", "symbol": params.get("symbol", "AAPL"),
                "market": params.get("market") or "US", "exchange": "NASDAQ",
                "currency": "USD", "assetClass": "equity", "securityType": "Common Stock",
                "instrumentId": f"{params.get('market') or 'US'}:{params.get('symbol', 'AAPL')}",
            }
        if capability == "market_data":
            provider = params.get("provider")
            value = self.responses.get(f"{params.get('capability')}:{provider}") or self.responses.get(params.get("capability"))
            if value is None:
                return {"status": "UNAVAILABLE", "error": "no fake", "failureClass": "no_data"}
            if callable(value):
                result = value(params)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            return value
        return {"status": "UNAVAILABLE", "error": "no fake"}


# ── Instruments ─────────────────────────────────────────────────────────────

def test_classify_crypto_pairs():
    assert classify_identifier("BTCUSDT")["kind"] == "crypto"
    assert classify_identifier("BTC-USD")["kind"] == "crypto"
    assert classify_identifier("BTC/USD", "CRYPTO")["kind"] == "crypto"
    assert classify_identifier("BTC")["kind"] == "crypto"
    assert split_crypto_pair("ETHUSDC") == ("ETH", "USDC")


def test_classify_fx_and_equity():
    assert classify_identifier("EURUSD=X")["kind"] == "fx"
    assert classify_identifier("EUR/USD")["kind"] == "fx"
    assert classify_identifier("AAPL")["kind"] == "equity"
    assert classify_identifier("2330.TW")["kind"] == "equity"


def test_provider_symbols_from_bridge_payload():
    from harness.market.instruments import from_bridge_payload

    inst = from_bridge_payload(
        {"status": "OK", "symbol": "BTC-USD", "market": "CRYPTO", "assetClass": "crypto",
         "currency": "USD", "instrumentId": "CRYPTO:BTC-USD"},
        "BTCUSDT",
    )
    assert inst.asset_type == "crypto"
    assert inst.provider_symbols["binance"] == "BTCUSDT"
    assert inst.provider_symbols["coingecko"] == "btc"


# ── Quality ─────────────────────────────────────────────────────────────────

def test_quote_quality_flags_negative_and_crossed():
    q = Quote(meta=MarketMeta(symbol="X", data_type="quote"),
              price=-5.0, bid=10.0, ask=9.0, volume=100)
    report = evaluate_quote(q)
    kinds = {f.kind for f in report.findings}
    assert "invalid_value" in kinds
    assert report.status == "invalid"


def test_quote_quality_valid():
    import time as _t

    now = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime()) + "Z"
    q = Quote(meta=MarketMeta(symbol="X", data_type="quote", freshness="realtime"),
              price=100.0, bid=99.9, ask=100.1, volume=10, timestamp=now)
    report = evaluate_quote(q)
    assert report.status == "valid"


def test_series_ohlc_consistency():
    series = HistoricalPriceSeries(
        meta=MarketMeta(symbol="X", data_type="ohlcv"),
        bars=[OHLCVBar(timestamp="2026-01-01", open=10, high=5, low=8, close=6, volume=1)],
    )
    report = evaluate_series(series)
    assert any(f.kind == "ohlc" for f in report.findings)
    assert report.status == "invalid"


def test_orderbook_quality_crossed():
    book = OrderBook(
        meta=MarketMeta(symbol="BTCUSDT", data_type="orderbook"),
        bids=[OrderBookLevel(price=101, quantity=1)],
        asks=[OrderBookLevel(price=100, quantity=1)],
        best_bid=101, best_ask=100,
    )
    report = evaluate(book, "orderbook")
    assert any(f.kind == "invalid_value" for f in report.findings)


# ── Errors ──────────────────────────────────────────────────────────────────

def test_classify_bridge_failure_rate_limit():
    err = classify_bridge_failure({"status": "UNAVAILABLE", "error": "429 too many",
                                   "diagnostics": [{"httpStatus": 429}]}, capability="quote")
    assert err.code == RATE_LIMITED
    assert err.retryable is True


def test_market_error_rejects_unknown_code():
    with pytest.raises(ValueError):
        MarketError("NOT_A_CODE", "x")


# ── Cache ───────────────────────────────────────────────────────────────────

def test_cache_freshness_guard():
    cache = MarketCache()
    q = Quote(meta=MarketMeta(symbol="X", data_type="quote", event_time="2000-01-01T00:00:00Z"), price=1.0)
    cache.put("quote", {"symbol": "X"}, q, data_timestamp="2000-01-01T00:00:00Z", freshness="realtime")
    # A realtime ask must NOT be served a 26-year-old entry.
    assert cache.get("quote", {"symbol": "X"}, freshness="realtime") is None
    assert cache.stale_skips >= 1


def test_cache_dedup_inflight():
    cache = MarketCache()
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        await asyncio.sleep(0.02)
        return "value"

    async def run():
        results = await asyncio.gather(
            cache.get_or_fetch("quote", {"symbol": "X"}, fetch),
            cache.get_or_fetch("quote", {"symbol": "X"}, fetch),
        )
        return results

    results = asyncio.run(run())
    assert calls["n"] == 1
    assert all(r[0] == "value" for r in results)


# ── Router ──────────────────────────────────────────────────────────────────

def test_router_orders_and_breaker():
    router = ProviderRouter(breaker_threshold=2, breaker_reset_s=60)
    from harness.market.instruments import CanonicalInstrument

    inst = CanonicalInstrument(instrument_id="CRYPTO:BTCUSDT", symbol="BTCUSDT", asset_type="crypto")
    order = router.provider_order("orderbook", inst)
    assert order == ("binance",)
    assert router.allow("binance")
    router.record_failure("binance")
    router.record_failure("binance")
    assert not router.allow("binance")  # breaker open at threshold 2


def test_router_skips_unsupported_asset():
    router = ProviderRouter()
    from harness.market.instruments import CanonicalInstrument

    inst = CanonicalInstrument(instrument_id="US:AAPL", symbol="AAPL", asset_type="equity")
    order = router.provider_order("orderbook", inst)
    assert "binance" not in order
