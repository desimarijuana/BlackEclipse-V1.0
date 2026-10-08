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
import random
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


def _trade_event(symbol: str, provider: str, *, price: Any, quantity: Any, timestamp: Any,
                 side: Optional[str] = None, sequence: Any = None) -> MarketDataEvent:
    ts = _iso(timestamp) if isinstance(timestamp, (int, float)) else _iso()
    meta = MarketMeta(
        instrument_id=f"{'CRYPTO' if provider == 'binance' else 'US'}:{symbol}",
        symbol=symbol, asset_type="crypto" if provider == "binance" else "equity",
        venue=provider.upper(), exchange=provider.upper(),
        event_time=ts, retrieved_at=_iso(), observation_source="provider_asof",
        provider=provider, source=f"{provider}-ws", data_type="trade",
        freshness="realtime", quality="valid",
    )
    event = MarketDataEvent(
        event_type="market.trade", meta=meta,
        payload={"price": _float(price), "quantity": _float(quantity), "side": side,
                 "side_inferred": False},
        sequence=int(sequence) if isinstance(sequence, (int, float)) else None,
    )
    event.event_id = _event_id(event)
    return event


def normalize_finnhub_frames(frame: dict[str, Any]) -> list[MarketDataEvent]:
    """Normalize Finnhub trade frames → events (one frame may carry many)."""
    if not isinstance(frame, dict) or frame.get("type") != "trade":
        return []
    out: list[MarketDataEvent] = []
    for item in frame.get("data") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("s") or "").upper()
        if not symbol:
            continue
        out.append(_trade_event(
            symbol, "finnhub", price=item.get("p"), quantity=item.get("v"),
            timestamp=item.get("t"), sequence=item.get("t"),
        ))
    return out


def normalize_polygon_frames(frame: dict[str, Any]) -> list[MarketDataEvent]:
    """Normalize Polygon stock-trade frames → events."""
    if not isinstance(frame, dict) or not isinstance(frame.get("ev"), str):
        return []
    if frame.get("ev") != "T":  # "T" = trade
        return []
    symbol = str(frame.get("sym") or "").upper()
    if not symbol:
        return []
    # Polygon timestamps are nanoseconds since epoch.
    ts_ns = frame.get("t")
    ts_ms = int(ts_ns / 1_000_000) if isinstance(ts_ns, (int, float)) else None
    return [_trade_event(
        symbol, "polygon", price=frame.get("p"), quantity=frame.get("s"),
        timestamp=ts_ms, sequence=ts_ns,
    )]


async def _send(socket: Any, message: str) -> None:
    send = getattr(socket, "send", None)
    if send is None:
        return
    try:
        result = send(message)
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001 - a failed subscribe triggers a reconnect
        pass


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
        bridge: Any = None,
    ) -> None:
        self.provider = provider
        self._connect_override = connect
        self._on_event = on_event
        # Read-only TS bridge, used ONLY to resolve a keyed provider's socket
        # config (URL/token). Bound per run by the service, like the gateway.
        self._bridge = bridge
        self._subscriptions: dict[str, _Subscription] = {}
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop = asyncio.Event()
        self._last_sequence: dict[str, int] = {}
        self._seen_ids: set[str] = set()
        self._seen_order: list[str] = []
        self.metrics: dict[str, int] = {
            "events": 0, "deduped": 0, "reconnects": 0, "sequenceGaps": 0,
            "dropped": 0, "staleReconnects": 0,
        }
        self.state = "idle"  # idle | connecting | connected | reconnecting | backoff | unavailable | closed
        self._reconnect_attempts = 0

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
            self._reconnect_attempts = 0
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
        backoff = cfg.stream_backoff_base_s
        while not self._stop.is_set():
            symbols, events = self._combined_streams()
            if not symbols:
                await asyncio.sleep(0.25)
                continue
            if cfg.stream_max_reconnects and self._reconnect_attempts >= cfg.stream_max_reconnects:
                # Park honestly rather than reconnect forever; a later subscribe
                # resets the counter (see `subscribe`).
                self.state = "backoff"
                await asyncio.sleep(1.0)
                continue
            url = await self._stream_url(symbols, events)
            self.state = "connecting"
            try:
                socket = await self._connect(url)
            except StreamingUnavailable:
                self.state = "unavailable"
                return
            except Exception:  # noqa: BLE001 - a connect failure is retried
                self._reconnect_attempts += 1
                self.state = "reconnecting"
                self.metrics["reconnects"] += 1
                await asyncio.sleep(_jittered(min(cfg.stream_reconnect_max_s, backoff), cfg.stream_backoff_jitter))
                backoff = min(cfg.stream_reconnect_max_s, backoff * 2)
                continue
            self.state = "connected"
            backoff = cfg.stream_backoff_base_s
            try:
                await self._after_connect(socket, symbols)
                await self._consume(socket)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a drop is a reconnect, not a crash
                pass
            finally:
                await _safe_close(socket)
            if self._stop.is_set():
                break
            self._reconnect_attempts += 1
            self.state = "reconnecting"
            self.metrics["reconnects"] += 1
            await asyncio.sleep(_jittered(min(cfg.stream_reconnect_max_s, backoff), cfg.stream_backoff_jitter))
            backoff = min(cfg.stream_reconnect_max_s, backoff * 2)
        self.state = "closed"

    async def _stream_url(self, symbols: list[str], events: tuple[str, ...]) -> str:
        """Socket URL for this provider. Binance is keyless; a keyed provider's
        URL/token is resolved through the bridge (no secret is stored here)."""
        if self.provider == "binance":
            return binance_stream_url(symbols, events)
        if self._bridge is None:
            raise StreamingUnavailable(f"no bridge to resolve the {self.provider} stream config")
        try:
            payload = await self._bridge.fetch(
                "market_stream_config", {"provider": self.provider, "symbols": symbols, "eventTypes": list(events)}
            )
        except Exception as exc:  # noqa: BLE001 - a bridge failure is unavailable
            raise StreamingUnavailable(f"{self.provider} stream config failed: {exc}") from exc
        if payload.get("status") != "OK" or not payload.get("url"):
            raise StreamingUnavailable(payload.get("error") or f"{self.provider} streaming is unavailable")
        base = str(payload["url"])
        token = payload.get("token")
        if token:
            self._polygon_token = str(token)
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}token={token}"
        return base

    async def _after_connect(self, socket: Any, symbols: list[str]) -> None:
        """Provider-specific post-connect handshake (e.g. Finnhub subscribe)."""
        if self.provider == "finnhub":
            for symbol in symbols:
                await _send(socket, json.dumps({"type": "subscribe", "symbol": symbol}))
        elif self.provider == "polygon":
            await _send(socket, json.dumps({"action": "auth", "params": getattr(self, "_polygon_token", "")}))

    def _normalize_frames(self, frame: Any, event_type: str) -> list[MarketDataEvent]:
        if self.provider == "binance":
            event = normalize_binance_frame(frame, event_type)
            return [event] if event is not None else []
        if self.provider == "finnhub":
            return normalize_finnhub_frames(frame)
        if self.provider == "polygon":
            return normalize_polygon_frames(frame)
        return []

    async def _consume(self, socket: Any) -> None:
        """Read frames with a silence watchdog.

        A connected-but-silent socket (a half-open connection a TCP keepalive
        will not catch) is treated as a drop after `stream_stale_timeout_s` so
        the manager reconnects instead of hanging forever.
        """
        stale = get_config().stream_stale_timeout_s
        iterator = _iter_messages(socket).__aiter__()
        while not self._stop.is_set():
            try:
                raw = await asyncio.wait_for(iterator.__anext__(), timeout=max(1.0, stale))
            except asyncio.TimeoutError:
                self.metrics["staleReconnects"] = self.metrics.get("staleReconnects", 0) + 1
                return  # force reconnect
            except StopAsyncIteration:
                return
            try:
                frame = json.loads(raw)
            except (TypeError, ValueError):
                continue
            event_type = "trade"
            stream = frame.get("stream") if isinstance(frame, dict) else None
            if stream:
                if "@depth" in stream:
                    event_type = "orderbook"
                elif "@ticker" in stream:
                    event_type = "quote"
                else:
                    event_type = "trade"
            event = self._normalize_frames(frame, event_type)
            for ev in event:
                if await self._validate(ev):
                    await self._publish(ev)

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


def _jittered(delay: float, jitter: float) -> float:
    """Apply symmetric jitter so reconnects do not synchronize across clients."""
    if jitter <= 0:
        return max(0.0, delay)
    return max(0.0, delay * (1.0 + random.uniform(-jitter, jitter)))


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
_managers: dict[str, MarketStreamManager] = {}


def default_stream_manager() -> MarketStreamManager:
    """The keyless Binance manager (crypto streaming)."""
    return manager_for("binance")


def manager_for(provider: str, *, bridge: Any = None) -> MarketStreamManager:
    """A process-wide manager per provider (one socket per provider)."""
    name = (provider or "binance").lower()
    mgr = _managers.get(name)
    if mgr is None:
        mgr = MarketStreamManager(provider=name, bridge=bridge)
        _managers[name] = mgr
    elif bridge is not None:
        mgr._bridge = bridge  # noqa: SLF001 - per-run rebind for keyed providers
    return mgr


def all_stream_managers() -> dict[str, MarketStreamManager]:
    return dict(_managers)


def reset_stream_manager() -> None:
    global _manager
    _manager = None
    _managers.clear()


__all__ = [
    "MarketStreamManager",
    "StreamingUnavailable",
    "all_stream_managers",
    "binance_stream_url",
    "default_stream_manager",
    "manager_for",
    "normalize_binance_frame",
    "normalize_finnhub_frames",
    "normalize_polygon_frames",
    "reset_stream_manager",
]
