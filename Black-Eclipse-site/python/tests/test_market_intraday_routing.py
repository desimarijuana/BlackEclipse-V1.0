"""The live market-data path used by the quant engine.

Proves the two fixes that make real historical data loadable:
  * intraday crypto is sourced from Binance (not the date-collapsing yahoo path),
  * the provider's OWN ticker is forwarded (BTC-USD → BTCUSDT), so Binance is
    not asked for a symbol it does not trade.

No network: a recording bridge captures the exact bridge request.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.market.gateway import MarketDataGateway
from harness.market.router import ProviderRouter
from harness.tools import DataBridge


class RecordingBridge(DataBridge):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, capability: str, params: dict) -> dict:
        self.calls.append((capability, params))
        if capability == "market_snapshot":
            symbol = str(params.get("symbol", ""))
            if "-" in symbol or "/" in symbol or symbol.endswith("USDT"):
                return {"status": "UNAVAILABLE"}  # crypto/fx resolve locally
            return {"status": "OK", "symbol": symbol, "assetClass": "equity",
                    "market": "US", "instrumentId": f"US:{symbol}"}
        if capability == "market_data":
            return {
                "status": "OK", "provider": params.get("provider"),
                "symbol": params.get("symbol"), "interval": params.get("interval"),
                "series": [{"timestamp": "2024-01-01T00:00:00Z", "open": 1.0, "high": 2.0,
                            "low": 0.5, "close": 1.5, "volume": 10.0}],
            }
        return {"status": "UNAVAILABLE"}

    def market_data_calls(self) -> list[dict]:
        return [p for (cap, p) in self.calls if cap == "market_data"]


def _gateway() -> tuple[MarketDataGateway, RecordingBridge]:
    bridge = RecordingBridge()
    return MarketDataGateway(bridge, router=ProviderRouter()), bridge


def test_intraday_crypto_prefers_binance_with_its_own_ticker():
    gateway, bridge = _gateway()
    result = asyncio.run(gateway.get_historical_prices("BTC-USD", interval="1m"))
    calls = bridge.market_data_calls()
    assert calls, "expected a market_data bridge call"
    first = calls[0]
    assert first["provider"] == "binance"
    assert first["providerSymbols"] == {"binance": "BTCUSDT"}
    assert first["interval"] == "1m"
    # The returned series carries a real intraday timestamp (not a bare date).
    assert result.meta.symbol == "BTC-USD"
    assert result.bars and result.bars[0].timestamp.startswith("2024-01-01T00:00")


def test_daily_crypto_keeps_yahoo_first():
    gateway, bridge = _gateway()
    asyncio.run(gateway.get_historical_prices("BTC-USD", interval="1d"))
    first = bridge.market_data_calls()[0]
    assert first["provider"] == "yahoo"
    assert first["providerSymbols"] == {"yahoo": "BTC-USD"}


def test_intraday_equity_does_not_force_binance():
    gateway, bridge = _gateway()
    asyncio.run(gateway.get_historical_prices("AAPL", interval="1m"))
    first = bridge.market_data_calls()[0]
    assert first["provider"] != "binance"


def test_ohlcv_uses_the_same_routing():
    gateway, bridge = _gateway()
    asyncio.run(gateway.get_ohlcv("BTC-USD", interval="5m"))
    first = bridge.market_data_calls()[0]
    assert first["provider"] == "binance"
    assert first["providerSymbols"] == {"binance": "BTCUSDT"}
