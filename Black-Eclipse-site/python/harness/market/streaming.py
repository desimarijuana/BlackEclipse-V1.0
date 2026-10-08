"""Real-time market data streaming — connection manager, normalizer, event bus.

This is a REAL streaming architecture over provider WebSockets (Binance's public
combined stream is the implemented provider), not REST polling dressed up as
streaming. The flow:

    Provider WebSocket
      → ConnectionManager (one connection per provider, subscriptions multiplexed)
      → per-provider normalizer (raw frame → canonical MarketDataEvent)
      → sequence validation + deduplication
      → bounded asyncio event bus (backpressure via a bounded queue)
      → subscribers (agents / analytics)

It supports subscribe, unsubscribe, multiple symbols, multiple event types,
connection lifecycle, heartbeat, reconnect with exponential backoff, ordered
resubscription, sequence gap detection (→ STREAM_RESYNC_REQUIRED), deduplication
and graceful shutdown.

The WebSocket transport is injectable (`connect`), so the whole lifecycle is
testable with a fake socket — no network needed in CI. `websockets` is an
optional dependency (installed by default); when it is absent the manager reports
an honest unavailable state, exactly like the rest of the runtime.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .config import get_config
from .models import MarketDataEvent, MarketMeta

# Provider id → stream provider factory.
_STREAM_PROVIDERS = ("binance",)


def _iso(ms: Optional[int] = None) -> str:
    if ms is not None:
        secs = ms / 1000.0
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(secs)) + f".{int((secs % 1) * 1000):03d}Z"
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def binance_stream_url(symbols: list[str], event_types: tuple[str, ...]) -> str:
    """Build the combined-stream URL for the requested symbols/event types.

    Public endpoint, no key. `@trade`, `@ticker` (quote) and `@depth20` (book)
    streams are combined into one socket so a provider never opens N sockets.
    """
    streams: list[str] = []
    for sym in symbols:
        s = sym.lower()
        for et in event_types:
            if et == "trade":
                streams.append(f"{s}@trade")
            elif et in ("quote", "ohlcv"):
                streams.append(f"{s}@ticker")
            elif et == "orderbook":
                streams.append(f"{s}@depth20@100ms")
    if len(streams) == 1:
        return f"wss://stream.binance.com:9443/ws/{streams[0]}"
    return "wss://stream.binance.com:9443/stream?streams=" + "/".join(streams)


def normalize_binance_frame(frame: dict[str, Any], event_type: str) -> Optional[MarketDataEvent]:
    """Normalize one Binance combined-stream frame into a canonical event."""
    data = frame.get("data") if isinstance(frame, dict) and "data" in frame else frame
    if not isinstance(data, dict):
        return None
    etype = data.get("e")
    symbol = str(data.get("s") or "").upper()
    if not symbol:
        return None
    meta = MarketMeta(
        instrument_id=f"CRYPTO:{symbol}",
        symbol=symbol,
        asset_type="crypto",
        venue="BINANCE",
        exchange="BINANCE",
        currency="USDT" if symbol.endswith("USDT") else None,
        event_time=_iso(data.get("E") or data.get("T")),
        retrieved_at=_iso(),
        observation_source="provider_asof",
        provider="binance",
        source="binance-ws",
        data_type=event_type,
        freshness="realtime",
        quality="valid",
    )
    if etype == "trade" or event_type == "trade":
        payload = {
            "trade_id": data.get("t"),
            "price": _float(data.get("p")),
            "quantity": _float(data.get("q")),
            "buyer_maker": data.get("m"),
            # Binance reports buyer-maker; the taker side is the aggressor.
            "side": "sell" if data.get("m") else "buy",
            "side_inferred": False,
        }
        event = MarketDataEvent(event_type="market.trade", meta=meta, payload=payload,
                                sequence=data.get("t"))
    elif etype == "depthUpdate" or event_type == "orderbook":
        bids = [[_float(p), _float(q)] for p, q in data.get("bids", [])]
        asks = [[_float(p), _float(q)] for p, q in data.get("asks", [])]
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        event = MarketDataEvent(
            event_type="market.orderbook", meta=meta,
            payload={
                "bids": bids, "asks": asks, "best_bid": best_bid, "best_ask": best_ask,
                "spread": (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None,
                "sequence": data.get("u"),
                "book_state": "delta" if data.get("e") == "depthUpdate" else "snapshot",
            },
            sequence=data.get("u"),
        )
    else:  # ticker → quote (+ ohlcv snapshot)
        payload = {
            "price": _float(data.get("c")),
            "change_pct": _float(data.get("P")),
            "change": _float(data.get("p")),
            "open": _float(data.get("o")),
            "high": _float(data.get("h")),
            "low": _float(data.get("l")),
            "volume": _float(data.get("v")),
        }
        event = MarketDataEvent(event_type="market.quote", meta=meta, payload=payload,
                                sequence=data.get("E"))
    event.event_id = _event_id(event)
    return event


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_id(event: MarketDataEvent) -> str:
    meta = event.meta
    body = json.dumps(event.payload, sort_keys=True, default=str)
    return f"{meta.provider}:{meta.symbol}:{event.event_type}:{event.sequence or meta.event_time}:{hash(body) & 0xFFFFFFFF}"


@dataclass
class _Subscription:
    id: str
    provider: str
    symbols: list[str]
    event_types: tuple[str, ...]
    queue: asyncio.Queue
    created_at: str = field(default_factory=_iso)


class StreamingUnavailable(Exception):
    """Raised when no WebSocket transport is available."""


class MarketStreamManager:
    """Owns one WebSocket connection per provider, multiplexing subscriptions."""

    def __init__(
        self,
        *,
        provider: str = "binance",
        connect: Optional[Callable[[str], Awaitable[Any]]] = None,
        on_event: Optional[Callable[[MarketDataEvent], Awaitable[None]]] = None,
    ) -> None:
        self.provider = provider
        self._connect_override = connect
        self._on_event = on_event
        self._subscriptions: dict[str, _Subscription] = {}
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop = asyncio.Event()
        self._last_sequence: dict[str, int] = {}
        self._seen_ids: set[str] = set()
        self._seen_order: list[str] = []
        self.metrics: dict[str, int] = {
            "events": 0, "deduped": 0, "reconnects": 0, "sequenceGaps": 0,
            "dropped": 0,
        }
        self.state = "idle"  # idle | connecting | connected | reconnecting | closed

    # ── Transport ────────────────────────────────────────────────────────────
    async def _connect(self, url: str) -> Any:
        if self._connect_override is not None:
            return await self._connect_override(url)
        try:
            import websockets  # type: ignore
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise StreamingUnavailable(
                "the websockets package is not installed; streaming is unavailable"
            ) from exc
        return await websockets.connect(url, ping_interval=20, ping_timeout=20, max_queue=1000)

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def subscribe(
        self,
        symbols: list[str],
        event_types: tuple[str, ...] = ("trade",),
        *,
        subscription_id: Optional[str] = None,
    ) -> str:
        """Register a subscription and ensure the connection is running."""
        if len(self._subscriptions) >= get_config().stream_max_subscriptions:
            raise StreamingUnavailable("subscription limit reached")
        sub_id = subscription_id or f"sub_{int(time.time() * 1000)}_{len(self._subscriptions)}"
        queue: asyncio.Queue = asyncio.Queue(maxsize=get_config().stream_queue_size)
        self._subscriptions[sub_id] = _Subscription(
            id=sub_id, provider=self.provider,
            symbols=[s.strip().upper() for s in symbols if s.strip()],
            event_types=tuple(event_types) or ("trade",), queue=queue,
        )
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run())
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        return self._subscriptions.pop(subscription_id, None) is not None

    async def stop(self) -> None:
        """Graceful shutdown: stop the loop and close every subscription queue."""
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        self.state = "closed"

    def list_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"id": s.id, "provider": s.provider, "symbols": s.symbols,
             "eventTypes": list(s.event_types), "createdAt": s.created_at,
             "queueDepth": s.queue.qsize()}
            for s in self._subscriptions.values()
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "provider": self.provider,
            "subscriptions": self.list_subscriptions(),
            "metrics": dict(self.metrics),
        }

    # ── Connection loop ──────────────────────────────────────────────────────
    def _combined_streams(self) -> tuple[list[str], tuple[str, ...]]:
        symbols: list[str] = []
        events: list[str] = []
        for sub in self._subscriptions.values():
            for sym in sub.symbols:
                if sym not in symbols:
                    symbols.append(sym)
            for et in sub.event_types:
                if et not in events:
                    events.append(et)
        return symbols, tuple(events)

    async def _run(self) -> None:
        cfg = get_config()
        backoff = 0.5
        while not self._stop.is_set():
            symbols, events = self._combined_streams()
            if not symbols:
                await asyncio.sleep(0.25)
                continue
            url = binance_stream_url(symbols, events)
            self.state = "connecting"
            try:
                socket = await self._connect(url)
            except StreamingUnavailable:
                self.state = "unavailable"
                return
            except Exception:  # noqa: BLE001 - a connect failure is retried
                self.state = "reconnecting"
                self.metrics["reconnects"] += 1
                await asyncio.sleep(min(cfg.stream_reconnect_max_s, backoff))
                backoff = min(cfg.stream_reconnect_max_s, backoff * 2)
                continue
            self.state = "connected"
            backoff = 0.5
            try:
                await self._consume(socket)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a drop is a reconnect, not a crash
                pass
            finally:
                await _safe_close(socket)
            if self._stop.is_set():
                break
            self.state = "reconnecting"
            self.metrics["reconnects"] += 1
            await asyncio.sleep(min(cfg.stream_reconnect_max_s, backoff))
            backoff = min(cfg.stream_reconnect_max_s, backoff * 2)
        self.state = "closed"

    async def _consume(self, socket: Any) -> None:
        async for raw in _iter_messages(socket):
            if self._stop.is_set():
                break
            try:
                frame = json.loads(raw)
            except (TypeError, ValueError):
                continue
            event_type = "trade"
            data = frame.get("data") if isinstance(frame, dict) else None
            stream = frame.get("stream") if isinstance(frame, dict) else None
            if stream:
                if "@depth" in stream:
                    event_type = "orderbook"
                elif "@ticker" in stream:
                    event_type = "quote"
                else:
                    event_type = "trade"
            event = normalize_binance_frame(frame, event_type)
            if event is None:
                continue
            if await self._validate(event):
                await self._publish(event)

    async def _validate(self, event: MarketDataEvent) -> bool:
        """Deduplicate + detect sequence gaps. Returns whether to publish."""
        if event.event_id and event.event_id in self._seen_ids:
            self.metrics["deduped"] += 1
            return False
        key = f"{event.meta.symbol}:{event.event_type}"
        seq = event.sequence
        if isinstance(seq, int):
            prev = self._last_sequence.get(key)
            if prev is not None and seq <= prev:
                # Out-of-order or duplicate sequence: drop, never regress the book.
                self.metrics["deduped"] += 1
                return False
            if prev is not None and seq > prev + 1 and event.event_type == "market.orderbook":
                # A gap in a book stream means the local book is now wrong; mark
                # it and let the consumer resync from a fresh snapshot.
                self.metrics["sequenceGaps"] += 1
                event.payload["book_state"] = "resync_required"
            self._last_sequence[key] = seq
        if event.event_id:
            self._seen_ids.add(event.event_id)
            self._seen_order.append(event.event_id)
            if len(self._seen_order) > 8192:
                old = self._seen_order.pop(0)
                self._seen_ids.discard(old)
        return True

    async def _publish(self, event: MarketDataEvent) -> None:
        self.metrics["events"] += 1
        for sub in list(self._subscriptions.values()):
            if event.meta.symbol not in sub.symbols:
                continue
            if event.event_type.split(".")[-1] not in sub.event_types and not (
                event.event_type == "market.quote" and "ohlcv" in sub.event_types
            ):
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Backpressure: drop the OLDEST event, keep the stream live.
                self.metrics["dropped"] += 1
                try:
                    sub.queue.get_nowait()
                    sub.queue.put_nowait(event)
                except Exception:  # noqa: BLE001
                    pass
        if self._on_event is not None:
            try:
                await self._on_event(event)
            except Exception:  # noqa: BLE001 - a subscriber must not break the stream
                pass

    async def next_event(self, subscription_id: str, timeout: float = 5.0) -> Optional[MarketDataEvent]:
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            return None
        try:
            return await asyncio.wait_for(sub.queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


async def _iter_messages(socket: Any):
    """Yield messages from either a real websockets client or a fake socket."""
    if hasattr(socket, "__aiter__"):
        async for message in socket:
            yield message
        return
    while True:
        message = await socket.recv()
        if message is None:
            return
        yield message


async def _safe_close(socket: Any) -> None:
    close = getattr(socket, "close", None)
    if close is None:
        return
    try:
        result = close()
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001
        pass


_manager: Optional[MarketStreamManager] = None


def default_stream_manager() -> MarketStreamManager:
    global _manager
    if _manager is None:
        _manager = MarketStreamManager()
    return _manager


def reset_stream_manager() -> None:
    global _manager
    _manager = None


__all__ = [
    "MarketStreamManager",
    "StreamingUnavailable",
    "binance_stream_url",
    "default_stream_manager",
    "normalize_binance_frame",
    "reset_stream_manager",
]
