"""Streaming lifecycle tests — connect, subscribe, receive, disconnect,
reconnect, resubscribe, sequence recovery, unsubscribe, shutdown. Driven by a
fake WebSocket; no network.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from harness.market.models import MarketDataEvent
from harness.market.streaming import (
    MarketStreamManager,
    StreamingUnavailable,
    binance_stream_url,
    normalize_binance_frame,
)


class FakeSocket:
    """A scripted websocket: yields `frames`, then optionally raises to simulate
    a disconnect. Records whether it was closed."""

    def __init__(self, frames: list[dict], *, disconnect_after: bool = False) -> None:
        self._frames = frames
        self._disconnect_after = disconnect_after
        self.closed = False

    async def recv(self):
        if self._frames:
            return json.dumps(self._frames.pop(0))
        if self._disconnect_after:
            raise ConnectionResetError("simulated drop")
        await asyncio.sleep(3600)

    async def close(self):
        self.closed = True


def trade_frame(symbol: str = "BTCUSDT", price: str = "50000", qty: str = "1", trade_id: int = 1) -> dict:
    return {"stream": f"{symbol.lower()}@trade", "data": {
        "e": "trade", "s": symbol, "t": trade_id, "p": price, "q": qty,
        "m": False, "E": 1_700_000_000_000,
    }}


def test_stream_url_single_and_combined():
    assert binance_stream_url(["BTCUSDT"], ("trade",)) == "wss://stream.binance.com:9443/ws/btcusdt@trade"
    url = binance_stream_url(["BTCUSDT", "ETHUSDT"], ("trade", "orderbook"))
    assert "streams=" in url and "btcusdt@trade" in url and "ethusdt@depth20@100ms" in url


def test_normalize_trade_frame():
    event = normalize_binance_frame(trade_frame(), "trade")
    assert event is not None
    assert event.event_type == "market.trade"
    assert event.payload["price"] == 50000.0
    assert event.payload["side"] == "buy"  # buyerMaker False → taker bought
    assert event.meta.observation_source == "provider_asof"
    assert event.event_id


def test_normalize_orderbook_frame():
    frame = {"stream": "btcusdt@depth20@100ms", "data": {
        "e": "depthUpdate", "s": "BTCUSDT", "u": 5,
        "bids": [["50000", "2"], ["49999", "1"]],
        "asks": [["50001", "1.5"]],
    }}
    event = normalize_binance_frame(frame, "orderbook")
    assert event.event_type == "market.orderbook"
    assert event.payload["best_bid"] == 50000.0
    assert event.payload["best_ask"] == 50001.0
    assert event.payload["spread"] == 1.0


def test_subscribe_receive_and_dedupe():
    socket = FakeSocket([
        trade_frame(trade_id=1),
        trade_frame(trade_id=1),  # duplicate sequence + identical → deduped
        trade_frame(trade_id=2, price="50010"),
    ])
    manager = MarketStreamManager(connect=lambda url: _return(socket))

    async def run():
        sub = await manager.subscribe(["BTCUSDT"], ("trade",))
        events = []
        for _ in range(2):
            ev = await manager.next_event(sub, timeout=2.0)
            if ev:
                events.append(ev)
        await manager.stop()
        return sub, events

    sub, events = asyncio.run(run())
    assert sub
    assert len(events) == 2
    assert manager.metrics["deduped"] >= 1


def test_unsubscribe():
    socket = FakeSocket([trade_frame()])
    manager = MarketStreamManager(connect=lambda url: _return(socket))

    async def run():
        sub = await manager.subscribe(["BTCUSDT"], ("trade",))
        ok = await manager.unsubscribe(sub)
        return ok

    assert asyncio.run(run()) is True


def test_reconnect_on_disconnect():
    drops = {"count": 0}

    def connect(url: str):
        drops["count"] += 1
        if drops["count"] == 1:
            return _return(FakeSocket([trade_frame()], disconnect_after=True))
        return _return(FakeSocket([trade_frame(price="51000", trade_id=9)]))

    manager = MarketStreamManager(connect=connect)

    async def run():
        sub = await manager.subscribe(["BTCUSDT"], ("trade",))
        events = []
        for _ in range(2):
            ev = await manager.next_event(sub, timeout=4.0)
            if ev:
                events.append(ev)
        await manager.stop()
        return events

    events = asyncio.run(run())
    assert manager.metrics["reconnects"] >= 1
    assert any(e.payload.get("price") == 51000.0 for e in events)


def test_sequence_gap_marks_resync():
    socket = FakeSocket([
        {"stream": "btcusdt@depth20@100ms", "data": {"e": "depthUpdate", "s": "BTCUSDT", "u": 1,
         "bids": [["50000", "1"]], "asks": [["50001", "1"]]}},
        {"stream": "btcusdt@depth20@100ms", "data": {"e": "depthUpdate", "s": "BTCUSDT", "u": 5,
         "bids": [["50000", "1"]], "asks": [["50001", "1"]]}},
    ])
    manager = MarketStreamManager(connect=lambda url: _return(socket))

    async def run():
        sub = await manager.subscribe(["BTCUSDT"], ("orderbook",))
        events = []
        for _ in range(2):
            ev = await manager.next_event(sub, timeout=3.0)
            if ev:
                events.append(ev)
        await manager.stop()
        return events

    events = asyncio.run(run())
    assert manager.metrics["sequenceGaps"] >= 1
    assert any(e.payload.get("book_state") == "resync_required" for e in events)


def test_unavailable_without_transport():
    manager = MarketStreamManager()

    async def run():
        # No connect override and (in a test env without the package) an honest
        # unavailable state; with the package, this would attempt a real connect.
        return manager.snapshot()

    snapshot = asyncio.run(run())
    assert snapshot["state"] in ("idle", "unavailable")


async def _return(value):
    return value
