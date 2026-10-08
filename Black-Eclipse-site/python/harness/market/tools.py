"""Agent-facing market-data tools.

Fourteen tools, each calling the Market Data Gateway — never a provider. Names
match the directive exactly:

    get_quote, get_historical_prices, get_ohlcv, get_volume, get_orderbook,
    get_trades, get_market_cap, get_supply, get_funding_rate,
    get_open_interest, get_options_chain, get_fx_rate, get_bond_data,
    stream_market_data

Every tool:
  * returns a plain-text summary for the model plus a structured `data` dict,
  * carries provenance (provider, timestamps, quality) into the run's source
    collector, so market data flows into the Evidence & Research Engine,
  * returns a structured error (never a fabricated value) when data is absent,
  * respects an explicit `freshness` requirement and says so when unsatisfiable.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from .errors import MarketError
from .gateway import MarketDataGateway
from .instruments import ContractTerms
from .models import MarketRecord
from .provenance import to_evidence

_FRESHNESS_CLASSES = {"realtime", "intraday", "daily", "slow", "any"}

# Freshness phrases → a canonical class. A numeric ceiling is mapped to the
# nearest class; the gateway then enforces that class.
_FRESHNESS_HINTS = [
    (60, "realtime"),
    (15 * 60, "intraday"),
    (24 * 3600, "daily"),
    (7 * 24 * 3600, "slow"),
]


def _parse_freshness(raw: Any) -> str:
    if raw is None:
        return "any"
    text = str(raw).strip().lower()
    if text in _FRESHNESS_CLASSES:
        return text
    # "60 seconds" / "5 min" / "1 hour" → a class.
    seconds = _parse_duration(text)
    if seconds is not None:
        for ceiling, cls in _FRESHNESS_HINTS:
            if seconds <= ceiling:
                return cls
        return "slow"
    return "any"


def _parse_duration(text: str) -> Optional[float]:
    import re

    match = re.match(r"^(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days)?$", text)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "s")[0]
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    return value


def _gateway(ctx: Any) -> MarketDataGateway:
    """Get (or lazily build) the run's market-data gateway."""
    gateway = getattr(ctx, "market_gateway", None)
    if gateway is not None:
        return gateway
    gateway = MarketDataGateway(getattr(ctx, "data_bridge", None))
    try:
        ctx.market_gateway = gateway  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - context may be frozen in tests
        pass
    return gateway


def _collect(ctx: Any, record: MarketRecord, capability: str) -> None:
    """Hand a market record's provenance to the run's source collector."""
    sink = getattr(ctx, "source_sink", None)
    if sink is None:
        return
    try:
        evidence = to_evidence(record, capability)
        # The sink expects a retrieval-shaped result; wrap the evidence in a
        # minimal object exposing `.evidence` and `.data`.
        _StructuredResult = _make_sink_result(record, evidence)
        sink.add(_StructuredResult)
    except Exception:  # noqa: BLE001 - provenance collection must never break a tool
        pass


def _make_sink_result(record: MarketRecord, evidence: Any) -> Any:
    """A duck-typed retrieval result so the standard collector accepts it."""
    from ..retrieval.contract import FinancialRetrievalResult

    return FinancialRetrievalResult(
        status="OK",
        objective=f"{record.meta.data_type} {record.meta.symbol}",
        dataType="current_quote" if record.meta.data_type == "quote" else "historical_prices",
        instrument=record.meta.symbol,
        data=record.to_dict(),
        evidence=[evidence],
        sourceReferences=[evidence.source],
        quality=record.meta.quality,  # type: ignore[arg-type]
        retrievedAt=record.meta.retrieved_at,
    )


def _persist(ctx: Any, record: MarketRecord, capability: str) -> None:
    store = getattr(ctx, "market_store", None)
    if store is None:
        return
    try:
        store.save_snapshot(capability, record)
        # Data-quality findings ride the record's warnings; persist them so an
        # operator can see what the quality engine flagged (best-effort).
        if record.meta.warnings:
            store.record_quality(
                capability, record.meta.symbol, record.meta.provider,
                findings=[{"kind": "quality", "severity": "warning", "detail": w}
                          for w in record.meta.warnings],
                conflict=record.conflict,
            )
    except Exception:  # noqa: BLE001 - persistence is best-effort
        pass


def _render(record: MarketRecord, capability: str) -> str:
    meta = record.meta
    lines = [
        f"{capability.upper()} — {meta.symbol or '?'}"
        + (f" on {meta.venue or meta.exchange}" if (meta.venue or meta.exchange) else ""),
        f"Provider: {meta.provider or 'unknown'} | Status: {meta.data_status} | Quality: {meta.quality}",
        f"As of: {meta.event_time or 'unknown'} | Retrieved: {meta.retrieved_at}"
        + (f" | Currency: {meta.currency}" if meta.currency else ""),
    ]
    if record.conflict:
        lines.append(f"CONFLICT: {json.dumps(record.conflict)[:600]}")
    if meta.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in meta.warnings[:8])
    lines.append("")
    lines.append(_render_payload(record, capability))
    return "\n".join(lines)


def _render_payload(record: MarketRecord, capability: str) -> str:
    if capability in ("historical", "ohlcv"):
        bars = getattr(record, "bars", []) or []
        head = bars[:5]
        tail = bars[-3:] if len(bars) > 8 else []
        parts = [f"  {len(bars)} bar(s), interval={getattr(record, 'interval', None) or '?'}"]
        if getattr(record, "aggregation", None):
            parts.append(f"  aggregation: {record.aggregation}")
        for bar in head:
            parts.append(f"  {bar.timestamp} O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
        if tail:
            parts.append("  …")
            for bar in tail:
                parts.append(f"  {bar.timestamp} O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
        return "\n".join(parts)
    if capability == "orderbook":
        bids = getattr(record, "bids", [])[:5]
        asks = getattr(record, "asks", [])[:5]
        parts = [
            f"  best bid={record.best_bid} best ask={record.best_ask} spread={record.spread} "
            f"spread_bps={record.spread_bps}",
            f"  bid_depth={record.bid_depth} ask_depth={record.ask_depth} imbalance={record.imbalance}",
        ]
        parts.append("  bids: " + ", ".join(f"{l.price}x{l.quantity}" for l in bids))
        parts.append("  asks: " + ", ".join(f"{l.price}x{l.quantity}" for l in asks))
        return "\n".join(parts)
    if capability == "trades":
        trades = getattr(record, "trades", [])[:10]
        parts = [f"  {len(getattr(record, 'trades', []))} trade(s)"]
        for t in trades:
            parts.append(f"  {t.timestamp} {t.price} x {t.quantity} {t.side or ''}")
        return "\n".join(parts)
    if capability == "options":
        contracts = getattr(record, "contracts", [])
        parts = [f"  {len(contracts)} contract(s); expirations: {', '.join(getattr(record, 'expirations', [])[:6])}"]
        for c in contracts[:12]:
            parts.append(
                f"  {c.expiration} {c.option_type} {c.strike} bid={c.bid} ask={c.ask} "
                f"IV={c.implied_volatility} OI={c.open_interest}"
            )
        return "\n".join(parts)
    # Scalar records: render non-null top-level fields.
    data = record.model_dump(mode="json", exclude_none=True)
    fields = {k: v for k, v in data.items() if k not in ("meta", "raw", "conflict")
              and isinstance(v, (int, float, str))}
    return "\n".join(f"  {k}: {v}" for k, v in list(fields.items())[:40])


def _finish(ctx: Any, result: Any, capability: str) -> tuple[str, Any]:
    """Uniform result handling for a capability call."""
    if isinstance(result, MarketError):
        return (
            f"UNAVAILABLE — {result.code}: {result.message}"
            + (f" (provider={result.provider})" if result.provider else "")
            + (" This may be retryable." if result.retryable else ""),
            {"status": "UNAVAILABLE", "error": result.to_dict()},
        )
    _collect(ctx, result, capability)
    _persist(ctx, result, capability)
    return _render(result, capability), {"status": result.meta.data_status, **result.to_dict()}


# ── Handlers ────────────────────────────────────────────────────────────────

async def get_quote(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    freshness = _parse_freshness(args.get("freshness") or args.get("freshness_requirement"))
    result = await _gateway(ctx).get_quote(
        str(args.get("symbol", "")), args.get("market"),
        freshness=freshness if args.get("freshness") or args.get("freshness_requirement") else "realtime",
    )
    return _finish(ctx, result, "quote")


async def get_historical_prices(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_historical_prices(
        str(args.get("symbol", "")), args.get("market"),
        start=args.get("start"), end=args.get("end"),
        interval=str(args.get("interval") or "1d"),
        adjusted=bool(args.get("adjusted", True)),
        freshness=_parse_freshness(args.get("freshness") or "slow"),
    )
    return _finish(ctx, result, "historical")


async def get_ohlcv(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_ohlcv(
        str(args.get("symbol", "")), args.get("market"),
        start=args.get("start"), end=args.get("end"),
        interval=str(args.get("interval") or "1d"),
        adjusted=bool(args.get("adjusted", True)),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "ohlcv")


async def get_volume(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_volume(
        str(args.get("symbol", "")), args.get("market"),
        window=str(args.get("window") or "1d"),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "volume")


async def get_orderbook(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_orderbook(
        str(args.get("symbol", "")), args.get("market"),
        depth=int(args.get("depth") or 20),
        freshness=_parse_freshness(args.get("freshness") or "realtime"),
    )
    return _finish(ctx, result, "orderbook")


async def get_trades(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_trades(
        str(args.get("symbol", "")), args.get("market"),
        limit=int(args.get("limit") or 100),
        start=args.get("start"), end=args.get("end"),
        freshness=_parse_freshness(args.get("freshness") or "realtime"),
    )
    return _finish(ctx, result, "trades")


async def get_market_cap(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_market_cap(
        str(args.get("symbol", "")), args.get("market"),
        freshness=_parse_freshness(args.get("freshness") or "daily"),
    )
    return _finish(ctx, result, "market_cap")


async def get_supply(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_supply(
        str(args.get("symbol", "")), args.get("market"),
        freshness=_parse_freshness(args.get("freshness") or "daily"),
    )
    return _finish(ctx, result, "supply")


async def get_funding_rate(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_funding_rate(
        str(args.get("symbol", "")), args.get("market"),
        exchange=args.get("exchange"), history=int(args.get("history") or 0),
        freshness=_parse_freshness(args.get("freshness") or "realtime"),
    )
    return _finish(ctx, result, "funding")


async def get_open_interest(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_open_interest(
        str(args.get("symbol", "")), args.get("market"),
        exchange=args.get("exchange"), window=str(args.get("window") or "24h"),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "open_interest")


async def get_options_chain(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_options_chain(
        str(args.get("symbol", "")), args.get("market"),
        expiration=args.get("expiration"), greeks=bool(args.get("greeks", False)),
        freshness=_parse_freshness(args.get("freshness") or "daily"),
    )
    return _finish(ctx, result, "options")


async def get_fx_rate(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_fx_rate(
        base=args.get("base"), quote=args.get("quote"), symbol=args.get("symbol"),
        freshness=_parse_freshness(args.get("freshness") or "realtime"),
    )
    return _finish(ctx, result, "fx")


async def get_bond_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_bond_data(
        str(args.get("symbol", "")), args.get("market"),
        series_type=args.get("series_type") or args.get("seriesType"),
        freshness=_parse_freshness(args.get("freshness") or "slow"),
    )
    return _finish(ctx, result, "bonds")


async def stream_market_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Subscribe to / sample / inspect a real-time market stream.

    Actions:
      * `sample` (default) — subscribe, collect up to `count` events for at most
        `duration_seconds`, then unsubscribe and return the events.
      * `subscribe` — register a persistent subscription; returns its id.
      * `unsubscribe` — remove a subscription by id.
      * `snapshot` — list live subscriptions + stream metrics.
    """
    from .streaming import StreamingUnavailable, default_stream_manager

    action = str(args.get("action") or "sample").strip().lower()
    manager = getattr(ctx, "market_stream", None) or default_stream_manager()

    if action == "snapshot":
        return _render_stream(manager.snapshot()), {"status": "OK", **manager.snapshot()}

    if action == "unsubscribe":
        sub_id = str(args.get("subscription_id") or "")
        removed = await manager.unsubscribe(sub_id)
        return (
            f"Unsubscribed {'ok' if removed else 'not found'}: {sub_id}",
            {"status": "OK" if removed else "UNAVAILABLE", "subscriptionId": sub_id, "removed": removed},
        )

    symbols = args.get("symbols") or ([args["symbol"]] if args.get("symbol") else [])
    symbols = [str(s).upper() for s in symbols]
    if not symbols:
        return ("UNAVAILABLE — at least one symbol is required.",
                {"status": "UNAVAILABLE", "error": MarketError("INVALID_REQUEST", "symbols required").to_dict()})
    event_types = tuple(args.get("event_types") or ["trade"])
    event_types = tuple(str(e).lower() for e in event_types)

    try:
        sub_id = await manager.subscribe(symbols, event_types, subscription_id=args.get("subscription_id"))
    except StreamingUnavailable as exc:
        return (
            f"UNAVAILABLE — streaming is not available: {exc}",
            {"status": "UNAVAILABLE",
             "error": MarketError("STREAM_DISCONNECTED", str(exc)).to_dict()},
        )

    if action == "subscribe":
        return (
            f"Subscribed {symbols} to {', '.join(event_types)}. Subscription id: {sub_id}.",
            {"status": "OK", "subscriptionId": sub_id, "symbols": symbols,
             "eventTypes": list(event_types)},
        )

    # sample
    count = max(1, min(int(args.get("count") or 5), 50))
    duration = max(1.0, min(float(args.get("duration_seconds") or 8.0), 20.0))
    events: list[dict[str, Any]] = []
    deadline = asyncio.get_event_loop().time() + duration
    while len(events) < count:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        event = await manager.next_event(sub_id, timeout=min(remaining, 2.0))
        if event is None:
            continue
        events.append(event.to_dict())
    await manager.unsubscribe(sub_id)
    status = "OK" if events else "UNAVAILABLE"
    text = (
        f"Sampled {len(events)} stream event(s) for {', '.join(symbols)} "
        f"({', '.join(event_types)}) in {duration:.0f}s."
        + ("" if events else " No events arrived — the market may be closed or the stream rejected the subscription.")
    )
    return text, {
        "status": status,
        "subscriptionId": sub_id,
        "eventCount": len(events),
        "events": events,
        "streamState": manager.state,
    }


def _render_stream(snapshot: dict[str, Any]) -> str:
    lines = [
        f"Stream state: {snapshot.get('state')} (provider {snapshot.get('provider')})",
        f"Subscriptions: {len(snapshot.get('subscriptions') or [])}",
    ]
    for sub in snapshot.get("subscriptions") or []:
        lines.append(f"  - {sub['id']}: {', '.join(sub['symbols'])} {sub['eventTypes']}")
    lines.append(f"Metrics: {json.dumps(snapshot.get('metrics') or {})}")
    return "\n".join(lines)


# ── Registration ────────────────────────────────────────────────────────────

def register_market_tools(registry: Any) -> None:
    """Register the fourteen market-data tools on the shared registry."""
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any], timeout: int) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=handler, permission="read", risk="low", timeout_ms=timeout,
        ))

    _def(
        "get_quote",
        "Get the latest price/quote for an instrument (equity, ETF, crypto, FX). "
        "Selects the best structured provider; never invents a price. Pass `freshness` "
        "(e.g. 'realtime' or '60 seconds') to require freshness; if it cannot be met the "
        "result is UNAVAILABLE rather than a silently stale price.",
        get_quote,
        {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Ticker / pair, e.g. AAPL or BTC-USD."},
            "market": {"type": "string", "description": "Optional market code (US, PK, CRYPTO, FX…)."},
            "freshness": {"type": "string", "description": "Optional: realtime | intraday | daily | slow | '60 seconds'."},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_historical_prices",
        "Get a historical price series (adjusted OHLCV) over a date range. Requires a precise "
        "structured source; never searches the web for prices.",
        get_historical_prices,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "start": {"type": "string", "description": "Start date YYYY-MM-DD."},
            "end": {"type": "string", "description": "End date YYYY-MM-DD."},
            "interval": {"type": "string", "description": "1m,5m,15m,30m,1h,4h,1d,1w,1mo."},
            "adjusted": {"type": "boolean", "description": "Adjust for corporate actions (default true)."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        30_000,
    )
    _def(
        "get_ohlcv",
        "Get normalized OHLCV bars for an instrument at a given interval. Provider-native "
        "only; if Eclipse aggregates a finer series the result is labelled as aggregated.",
        get_ohlcv,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "start": {"type": "string"}, "end": {"type": "string"},
            "interval": {"type": "string", "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]},
            "adjusted": {"type": "boolean"}, "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        30_000,
    )
    _def(
        "get_volume",
        "Get volume statistics (total, average, relative, buy/sell where available). Clearly "
        "distinguishes provider-native metrics from Eclipse-derived ones.",
        get_volume,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "window": {"type": "string", "description": "1d, 5d, 1mo…"},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_orderbook",
        "Get a real order-book snapshot (bids/asks, spread, depth, imbalance) for a crypto/FX/"
        "derivative instrument. Not available for equities on the configured providers.",
        get_orderbook,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "depth": {"type": "integer", "description": "Levels per side (default 20)."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_trades",
        "Get the recent trade tape for an instrument (price, quantity, side, exchange). Side is "
        "only reported when the provider supplies it; an inferred side is labelled as such.",
        get_trades,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "limit": {"type": "integer", "description": "Max trades (default 100)."},
            "start": {"type": "string"}, "end": {"type": "string"}, "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        20_000,
    )
    _def(
        "get_market_cap",
        "Get an instrument's market capitalisation, price and shares outstanding. The share "
        "basis (basic/diluted/current/float) is stated; it is never mixed silently.",
        get_market_cap,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"}, "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_supply",
        "Get crypto supply data (circulating, total, max, FDV, circulating market cap).",
        get_supply,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"}, "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_funding_rate",
        "Get the perpetual-futures funding rate, funding interval and next funding time. An "
        "annualized figure is always labelled as derived, never confused with the raw rate.",
        get_funding_rate,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "exchange": {"type": "string"},
            "history": {"type": "integer", "description": "Number of historical points (0 = none)."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_open_interest",
        "Get open interest (contracts + USD) and its change for a derivatives instrument. "
        "Provider-native vs Eclipse-derived fields are labelled.",
        get_open_interest,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "exchange": {"type": "string"}, "window": {"type": "string"},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_options_chain",
        "Get an options chain (expirations, strikes, calls/puts, IV and Greeks where available). "
        "A missing Greek is reported as unavailable, never as zero.",
        get_options_chain,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"},
            "expiration": {"type": "string", "description": "Filter to one expiration YYYY-MM-DD."},
            "greeks": {"type": "boolean", "description": "Request Greeks when the provider can supply them."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        20_000,
    )
    _def(
        "get_fx_rate",
        "Get a foreign-exchange rate (bid/ask/mid) for a currency pair. Cross conversion is used "
        "when a direct rate is unavailable and is labelled as derived.",
        get_fx_rate,
        {"type": "object", "properties": {
            "base": {"type": "string", "description": "Base currency, e.g. USD."},
            "quote": {"type": "string", "description": "Quote currency, e.g. PKR."},
            "symbol": {"type": "string", "description": "Or a pair symbol, e.g. USDPKR=X."},
            "freshness": {"type": "string"},
        }},
        15_000,
    )
    _def(
        "get_bond_data",
        "Get normalized bond / Treasury data (price, yield, coupon, maturity, duration, spread, "
        "rating). Unsupported analytics are never fabricated.",
        get_bond_data,
        {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "e.g. US10Y, or a CUSIP/ISIN."},
            "market": {"type": "string"},
            "series_type": {"type": "string", "description": "treasury | corporate | government."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        20_000,
    )
    _def(
        "stream_market_data",
        "Subscribe to a real-time market stream (WebSocket, not polling). Actions: `sample` "
        "(default — collect a few events), `subscribe` (persistent), `unsubscribe`, `snapshot`. "
        "Supports multiple symbols and event types (trade, quote, orderbook, ohlcv).",
        stream_market_data,
        {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["sample", "subscribe", "unsubscribe", "snapshot"]},
            "symbol": {"type": "string", "description": "A single instrument to stream."},
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "Multiple instruments."},
            "event_types": {"type": "array", "items": {"type": "string"},
                            "description": "trade, quote, orderbook, ohlcv."},
            "count": {"type": "integer", "description": "Events to sample (default 5)."},
            "duration_seconds": {"type": "number", "description": "Sampling window (default 8s, max 20)."},
            "subscription_id": {"type": "string", "description": "For unsubscribe / reuse."},
        }},
        25_000,
    )


__all__ = ["register_market_tools"]
