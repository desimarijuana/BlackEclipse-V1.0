"""Provider adapter contract tests (recorded, sanitized payload shapes).

The runnable adapters live on the TS bridge; these tests pin the NORMALIZATION
contract the gateway relies on for each provider family, using representative
sanitized payloads. They do NOT claim live connectivity — a live smoke is opt-in
(`test_market_live.py`, BLACK_ECLIPSE_MARKET_LIVE=1) and requires credentials.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.market.cache import MarketCache
from harness.market.errors import MarketError
from harness.market.gateway import MarketDataGateway
from harness.market.providers import default_providers
from harness.market.router import ProviderRouter
from harness.market.verification import lineage_of
from harness.tools import DataBridge


class ShapeBridge(DataBridge):
    def __init__(self, payloads: dict[str, dict]) -> None:
        self.payloads = payloads

    async def fetch(self, capability: str, params: dict) -> dict:
        if capability == "market_snapshot":
            return {"status": "OK", "symbol": params.get("symbol", "AAPL"),
                    "market": params.get("market") or "US", "exchange": "X",
                    "currency": "USD", "assetClass": "equity",
                    "instrumentId": f"US:{params.get('symbol')}"}
        if capability == "market_data":
            key = f"{params.get('capability')}:{params.get('provider')}"
            payload = self.payloads.get(key)
            if payload is None:
                return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "no fixture"}
            return payload
        return {"status": "UNAVAILABLE", "error": "unknown"}


def _gw(payloads: dict[str, dict]) -> MarketDataGateway:
    return MarketDataGateway(ShapeBridge(payloads), cache=MarketCache(), router=ProviderRouter())


def _run(coro):
    return asyncio.run(coro)


def test_polygon_series_normalization():
    payload = {"status": "OK", "provider": "polygon", "interval": "1d", "adjusted": True,
               "series": [{"timestamp": "2026-01-02T00:00:00Z", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}]}
    result = _run(_gw({"historical:polygon": payload}).get_historical_prices("AAPL", provider="polygon"))
    assert not isinstance(result, MarketError)
    assert result.meta.provider == "polygon"
    assert result.bars[0].close == 11


def test_finnhub_quote_normalization():
    payload = {"status": "OK", "provider": "finnhub", "price": {"price": 237.42}, "asOf": "2026-01-02T15:00:00Z",
               "observationTime": "2026-01-02T15:00:00Z", "observationSource": "provider_asof"}
    result = _run(_gw({"quote:finnhub": payload}).get_quote("AAPL", provider="finnhub"))
    assert not isinstance(result, MarketError)
    assert result.price == 237.42
    assert result.meta.provider == "finnhub"


def test_coingecko_market_cap_normalization():
    payload = {"status": "OK", "provider": "coingecko", "marketCap": 1e12, "price": 50000.0}
    result = _run(_gw({"market_cap:coingecko": payload}).get_market_cap("BTC"))
    assert not isinstance(result, MarketError)
    assert result.market_cap == 1e12


def test_treasury_bond_normalization():
    payload = {"status": "OK", "provider": "treasury", "yield": 4.25, "maturity": "2036-01-01", "tenor": "10Y"}
    result = _run(_gw({"bonds:treasury": payload}).get_bond_data("US10Y"))
    assert not isinstance(result, MarketError)
    assert result.yield_ == 4.25


def test_unavailable_provider_is_not_silent_success():
    result = _run(_gw({}).get_quote("AAPL", provider="finnhub"))
    assert isinstance(result, MarketError)
    assert result.code in ("DATA_NOT_AVAILABLE", "PROVIDER_UNAVAILABLE", "SYMBOL_NOT_FOUND")


def test_every_provider_declares_lineage_and_timeliness():
    providers = default_providers()
    assert providers, "no providers declared"
    for p in providers:
        d = p.to_dict()
        assert d["timeliness"] in ("realtime", "delayed", "eod", "reference", "unknown")
        assert "entitlement" in d
        # A provider that participates in verification must declare its upstream.
        if p.id in ("yahoo", "binance", "coingecko", "stooq", "treasury", "fx", "polygon", "finnhub"):
            assert p.upstream, f"{p.id} must declare upstream lineage"
            assert lineage_of(p.id) == p.upstream, f"{p.id} upstream drift vs verification"
