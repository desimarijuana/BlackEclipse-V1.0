"""Opt-in LIVE market-data smoke/soak tests.

Skipped by default. Run with:

    set BLACK_ECLIPSE_MARKET_LIVE=1
    python -m pytest python/tests/test_market_live.py -q

These contact the real Binance public API and WebSocket to validate the frame
shapes the normalizers assume and that the connection manager survives a real
stream. They are deliberately NOT part of the offline suite.
"""

from __future__ import annotations

import asyncio
import os

import pytest

LIVE = os.environ.get("BLACK_ECLIPSE_MARKET_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="live market smoke is opt-in: set BLACK_ECLIPSE_MARKET_LIVE=1")


def test_binance_rest_shapes():
    """The fields the adapters read exist in the live responses."""
    import httpx

    with httpx.Client(timeout=15.0) as client:
        ticker = client.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"}).json()
        assert "lastPrice" in ticker and "priceChangePercent" in ticker
        depth = client.get("https://api.binance.com/api/v3/depth", params={"symbol": "BTCUSDT", "limit": 5}).json()
        assert isinstance(depth.get("bids"), list) and isinstance(depth.get("asks"), list)
        oi = client.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": "BTCUSDT"}).json()
        assert "openInterest" in oi


def test_binance_ws_soak_receives_events():
    """The real WebSocket delivers normalized events (a short live soak)."""
    from harness.market.streaming import MarketStreamManager

    manager = MarketStreamManager()

    async def run():
        loop = asyncio.get_event_loop()
        sub = await manager.subscribe(["BTCUSDT"], ("trade",))
        deadline = loop.time() + 20.0
        events = []
        while loop.time() < deadline and len(events) < 3:
            ev = await manager.next_event(sub, timeout=3.0)
            if ev is not None:
                events.append(ev)
        await manager.stop()
        return events

    events = asyncio.run(run())
    assert len(events) >= 1, "no live trade events arrived"
    assert events[0].event_type == "market.trade"
    assert events[0].payload.get("price")
    assert manager.metrics["events"] >= 1
