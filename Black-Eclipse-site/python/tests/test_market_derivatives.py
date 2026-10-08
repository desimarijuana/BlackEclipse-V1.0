"""Derived-market-analytics + keyed-provider/streaming tests.

Covers Black-Scholes option Greeks, bond duration/convexity, corporate-bond index
shapes, and the Finnhub/Polygon streaming normalizers + keyed stream URL. No
network.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any

from harness.market import bondmath, greeks
from harness.market.streaming import (
    MarketStreamManager,
    all_stream_managers,
    manager_for,
    normalize_finnhub_frames,
    normalize_polygon_frames,
    reset_stream_manager,
)
from harness.market.tools import register_market_tools
from harness.tools import DataBridge, ToolContext, ToolRegistry


# ── Black-Scholes Greeks ────────────────────────────────────────────────────

def test_black_scholes_put_call_parity():
    call = greeks.black_scholes(option_type="call", spot=100, strike=100, time_to_expiry=0.5, iv=0.2, risk_free=0.04)
    put = greeks.black_scholes(option_type="put", spot=100, strike=100, time_to_expiry=0.5, iv=0.2, risk_free=0.04)
    # C - P = S - K e^{-rT}
    expected = 100 - 100 * pow(2.718281828459045, -0.04 * 0.5)
    assert abs((call["price"] - put["price"]) - expected) < 0.05
    assert call["delta"] > 0 and put["delta"] < 0
    assert call["gamma"] > 0


def test_black_scholes_rejects_unusable_inputs():
    assert greeks.black_scholes(option_type="call", spot=0, strike=100, time_to_expiry=0.5, iv=0.2) is None
    assert greeks.black_scholes(option_type="call", spot=100, strike=100, time_to_expiry=0, iv=0.2) is None
    assert greeks.black_scholes(option_type="call", spot=100, strike=100, time_to_expiry=0.5, iv=0) is None


def test_years_to_expiry():
    future = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) + _dt.timedelta(days=365)).strftime("%Y-%m-%d")
    assert 0.9 < greeks.years_to_expiry(future) < 1.1
    assert greeks.years_to_expiry(None) is None


def test_enrich_options_greeks_fills_missing_only():
    from harness.market.models import MarketMeta, OptionsChain, OptionContract

    chain = OptionsChain(
        meta=MarketMeta(symbol="AAPL", data_type="options"),
        underlying_price=100.0,
        contracts=[
            OptionContract(expiration=(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) + _dt.timedelta(days=90)).strftime("%Y-%m-%d"),
                           strike=100, option_type="call", implied_volatility=0.25),
            OptionContract(expiration=(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) + _dt.timedelta(days=90)).strftime("%Y-%m-%d"),
                           strike=110, option_type="put", implied_volatility=0.3, delta=-0.123),
        ],
    )
    filled = greeks.enrich_options_greeks(chain, risk_free=0.04)
    assert filled == 2
    assert chain.contracts[0].delta is not None
    assert chain.contracts[0].greeks_source.startswith("calculated")
    # A provider-supplied Greek is never overwritten.
    assert chain.contracts[1].delta == -0.123


def test_enrich_options_greeks_leaves_none_without_inputs():
    from harness.market.models import MarketMeta, OptionsChain, OptionContract

    chain = OptionsChain(
        meta=MarketMeta(symbol="AAPL", data_type="options"),
        underlying_price=None,  # no spot → cannot compute
        contracts=[OptionContract(expiration="2030-01-01", strike=100, option_type="call", implied_volatility=0.25)],
    )
    assert greeks.enrich_options_greeks(chain) == 0
    assert chain.contracts[0].delta is None


# ── Bond analytics ──────────────────────────────────────────────────────────

def test_bond_analytics_known_par_bond():
    # A par bond (coupon == yield) has Macaulay ~ maturity and modified < Macaulay.
    r = bondmath.bond_analytics(coupon=5.0, yield_=5.0, years=10)
    assert abs(r["macaulay_duration"] - 8.0) < 0.6
    assert r["modified_duration"] < r["macaulay_duration"]
    assert r["convexity"] > 0


def test_enrich_bond_fills_and_respects_provider():
    from harness.market.models import BondData, MarketMeta

    bond = BondData(meta=MarketMeta(symbol="X", data_type="bonds"), coupon=4.0, yield_=4.5, maturity="2035-01-01")
    assert bondmath.enrich_bond(bond) is True
    assert bond.duration and bond.modified_duration and bond.convexity

    supplied = BondData(meta=MarketMeta(symbol="Y", data_type="bonds"),
                        coupon=4.0, yield_=4.5, maturity="2035-01-01", duration=7.77)
    bondmath.enrich_bond(supplied)
    assert supplied.duration == 7.77  # provider value preserved


# ── Streaming normalizers + keyed config ────────────────────────────────────

def test_finnhub_normalizer_expands_trades():
    frame = {"type": "trade", "data": [
        {"p": 189.1, "s": "AAPL", "t": 1_700_000_000_000, "v": 100},
        {"p": 189.2, "s": "AAPL", "t": 1_700_000_000_100, "v": 50},
    ]}
    events = normalize_finnhub_frames(frame)
    assert len(events) == 2
    assert events[0].event_type == "market.trade"
    assert events[0].payload["price"] == 189.1
    assert events[0].meta.asset_type == "equity"
    assert normalize_finnhub_frames({"type": "ping"}) == []


def test_polygon_normalizer():
    frames = [{"ev": "T", "sym": "AAPL", "p": 190.0, "s": 10, "t": 1_700_000_000_000_000_000}]
    events = normalize_polygon_frames(frames[0])
    assert len(events) == 1
    assert events[0].meta.provider == "polygon"
    assert events[0].payload["price"] == 190.0
    assert normalize_polygon_frames({"ev": "Q", "sym": "AAPL"}) == []


class _StreamBridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        return self.responses.get(capability, {"status": "UNAVAILABLE", "error": "no fake"})


def test_manager_for_resolves_finnhub_url_via_bridge():
    reset_stream_manager()
    bridge = _StreamBridge({"market_stream_config": {
        "status": "OK", "provider": "finnhub", "protocol": "finnhub",
        "url": "wss://ws.finnhub.io", "token": "SECRET",
    }})
    manager = manager_for("finnhub", bridge=bridge)
    assert manager.provider == "finnhub"

    async def run():
        return await manager._stream_url(["AAPL"], ("trade",))  # noqa: SLF001

    url = asyncio.run(run())
    assert url.startswith("wss://ws.finnhub.io?token=")
    assert all_stream_managers()["finnhub"] is manager
    reset_stream_manager()


def test_manager_reports_unavailable_without_key():
    reset_stream_manager()
    bridge = _StreamBridge({"market_stream_config": {
        "status": "UNAVAILABLE", "failureClass": "unconfigured", "error": "FINNHUB_API_KEY is not configured",
    }})
    manager = MarketStreamManager(provider="finnhub", bridge=bridge)

    async def run():
        try:
            await manager._stream_url(["AAPL"], ("trade",))  # noqa: SLF001
            return None
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    message = asyncio.run(run())
    assert message and "not configured" in message
    reset_stream_manager()


# ── Gateway: Greeks + corporate bond via a fake bridge ──────────────────────

class _GatewayBridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "market_snapshot":
            return {"status": "OK", "symbol": params.get("symbol"), "market": params.get("market") or "US",
                    "currency": "USD", "assetClass": "equity", "instrumentId": f"US:{params.get('symbol')}"}
        return self.responses.get(params.get("capability"), {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "no fake"})


def test_gateway_calculates_option_greeks():
    from harness.market.cache import MarketCache
    from harness.market.gateway import MarketDataGateway
    from harness.market.router import ProviderRouter

    exp = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) + _dt.timedelta(days=90)).strftime("%Y-%m-%d")
    payload = {
        "status": "OK", "provider": "yahoo", "symbol": "AAPL",
        "underlyingPrice": 100.0, "expirations": [exp],
        "contracts": [{"expiration": exp, "strike": 100, "type": "call",
                       "bid": 3.0, "ask": 3.2, "impliedVolatility": 0.3}],
        "observationTime": "2026-10-07T00:00:00Z", "observationSource": "provider_asof",
    }
    gw = MarketDataGateway(_GatewayBridge({"options": payload}), cache=MarketCache(), router=ProviderRouter())
    chain = asyncio.run(gw.get_options_chain("AAPL", "US", greeks=True))
    assert chain.contracts[0].delta is not None
    assert chain.contracts[0].greeks_source.startswith("calculated")


def test_gateway_corporate_bond_index_shape():
    from harness.market.cache import MarketCache
    from harness.market.gateway import MarketDataGateway
    from harness.market.router import ProviderRouter

    payload = {
        "status": "OK", "provider": "treasury", "symbol": "US_CORP_HY",
        "spread": 3.42, "yield": None, "seriesType": "corporate",
        "rating": "High Yield", "issuer": "ICE BofA US High Yield",
        "observationTime": "2026-10-06T00:00:00Z", "observationSource": "provider_asof",
    }
    gw = MarketDataGateway(_GatewayBridge({"bonds": payload}), cache=MarketCache(), router=ProviderRouter())
    bond = asyncio.run(gw.get_bond_data("US_CORP_HY", "US"))
    assert bond.series_type == "corporate"
    assert bond.spread == 3.42
    assert bond.rating == "High Yield"


def test_stream_tool_accepts_provider_argument():
    registry = ToolRegistry()
    register_market_tools(registry)
    tool = registry.get("stream_market_data")
    assert "provider" in tool.input_schema["properties"]
