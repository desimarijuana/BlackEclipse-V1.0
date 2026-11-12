"""Agent-facing market-data tools.

Eighteen tools, each calling the Market Data Gateway — never a provider. Names
match the directive exactly:

    get_quote, get_historical_prices, get_ohlcv, get_volume, get_orderbook,
    get_trades, get_market_cap, get_supply, get_funding_rate,
    get_open_interest, get_options_chain, get_fx_rate, get_bond_data,
    get_tvl, get_onchain_metric, get_liquidations, get_long_short_ratio,
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
        # The RECENT window is what an analysis needs: the first bar is shown
        # for context, and the last ten carry the present. Showing the OLDEST
        # bars (as this did) made a 5-year series read as 2021 data.
        head = bars[:1]
        tail = bars[-10:] if len(bars) > 1 else []
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
        # A refusal must TEACH its correction: the next route is named here,
        # so the agent collects the data instead of stopping at UNAVAILABLE.
        next_route = (
            " A scraper can collect this from the page that has it: call "
            "`scraper_run` with the source URL (the operator approves the site "
            "once) and label the rows SCRAPER-sourced."
        )
        # The WHOLE trail of providers, so the next call does not repeat a
        # route that already failed, and a provider that needs a credential it
        # does not have is never tried again.
        trail = ""
        tried = (result.detail or {}).get("providers") or []
        if tried:
            parts = [
                f"{entry.get('provider')}: {entry.get('code')}"
                + (f" ({str(entry.get('message'))[:90]})" if entry.get("message") else "")
                for entry in tried
                if isinstance(entry, dict)
            ]
            if parts:
                trail = " Providers tried: " + "; ".join(parts) + "."
        credential_note = ""
        if result.code == "AUTHENTICATION_FAILED":
            credential_note = (
                " That provider needs a credential it does not have - do not try it again."
            )
        from .quality_contract import DataQualityEnvelope

        return (
            f"UNAVAILABLE — {result.code}: {result.message}"
            + (f" (provider={result.provider})" if result.provider else "")
            + (" This may be retryable." if result.retryable else "")
            + trail
            + credential_note
            + next_route,
            {"status": "UNAVAILABLE", "error": result.to_dict(), "nextRoute": "scraper_run",
             "qualityVerdict": "UNAVAILABLE", "reasonCode": result.code,
             "envelope": DataQualityEnvelope(
                 provider=result.provider,
                 qualityVerdict="UNAVAILABLE",
                 routesSkipped=(result.detail or {}).get("providers") or [],
                 reasonCode=result.code,
             ).to_dict()},
        )
    _collect(ctx, result, capability)
    _persist(ctx, result, capability)
    from .quality_contract import envelope_from_record

    payload = {"status": result.meta.data_status, **result.to_dict()}
    envelope = envelope_from_record(result)
    payload["qualityVerdict"] = envelope.qualityVerdict
    payload["envelope"] = envelope.to_dict()
    if result.conflict:
        payload["conflict"] = result.conflict
    return _render(result, capability), payload


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


async def get_tvl(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_tvl(
        str(args.get("symbol", "")), args.get("market"),
        chain=args.get("chain"),
        freshness=_parse_freshness(args.get("freshness") or "daily"),
    )
    return _finish(ctx, result, "tvl")


async def get_onchain_metric(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_onchain_metric(
        str(args.get("address") or args.get("symbol") or ""),
        chain=str(args.get("chain") or "ethereum"),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "onchain")


async def get_liquidations(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_liquidations(
        str(args.get("symbol", "")), args.get("market"),
        exchange=args.get("exchange"), window=str(args.get("window") or "24h"),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "liquidations")


async def get_long_short_ratio(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = await _gateway(ctx).get_long_short_ratio(
        str(args.get("symbol", "")), args.get("market"),
        exchange=args.get("exchange"), interval=str(args.get("interval") or "1h"),
        limit=int(args.get("limit") or 48),
        freshness=_parse_freshness(args.get("freshness") or "intraday"),
    )
    return _finish(ctx, result, "long_short")


async def stream_market_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Subscribe to / sample / inspect a real-time market stream.

    Actions:
      * `sample` (default) — subscribe, collect up to `count` events for at most
        `duration_seconds`, then unsubscribe and return the events.
      * `subscribe` — register a persistent subscription; returns its id.
      * `unsubscribe` — remove a subscription by id.
      * `snapshot` — list live subscriptions + stream metrics.
    """
    from .streaming import (
        StreamingUnavailable,
        all_stream_managers,
        default_stream_manager,
        manager_for,
    )

    action = str(args.get("action") or "sample").strip().lower()
    symbols = args.get("symbols") or ([args["symbol"]] if args.get("symbol") else [])
    symbols = [str(s).upper() for s in symbols]

    if action == "snapshot":
        managers = all_stream_managers() or {"binance": default_stream_manager()}
        snapshot = {name: mgr.snapshot() for name, mgr in managers.items()}
        return _render_stream(snapshot), {"status": "OK", "managers": snapshot}

    # Resolve the provider: explicit, else auto (crypto-looking → binance, else
    # finnhub for equities when keyed).
    provider = str(args.get("provider") or "").strip().lower() or _default_stream_provider(symbols)
    manager = manager_for(provider, bridge=getattr(ctx, "data_bridge", None))
    if action == "unsubscribe":
        sub_id = str(args.get("subscription_id") or "")
        removed = await manager.unsubscribe(sub_id)
        return (
            f"Unsubscribed {'ok' if removed else 'not found'}: {sub_id}",
            {"status": "OK" if removed else "UNAVAILABLE", "subscriptionId": sub_id, "removed": removed},
        )

    if not symbols:
        return ("UNAVAILABLE — at least one symbol is required.",
                {"status": "UNAVAILABLE", "error": MarketError("INVALID_REQUEST", "symbols required").to_dict()})
    event_types = tuple(args.get("event_types") or ["trade"])
    event_types = tuple(str(e).lower() for e in event_types)

    try:
        sub_id = await manager.subscribe(symbols, event_types, subscription_id=args.get("subscription_id"))
    except StreamingUnavailable as exc:
        return (
            f"UNAVAILABLE — streaming is not available for {provider}: {exc}",
            {"status": "UNAVAILABLE",
             "error": MarketError("STREAM_DISCONNECTED", str(exc)).to_dict()},
        )

    if action == "subscribe":
        return (
            f"Subscribed {symbols} to {', '.join(event_types)} on {provider}. Subscription id: {sub_id}.",
            {"status": "OK", "subscriptionId": sub_id, "symbols": symbols,
             "eventTypes": list(event_types), "provider": provider},
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
        f"({', '.join(event_types)}) on {provider} in {duration:.0f}s."
        + ("" if events else " No events arrived — the market may be closed, the stream rejected the subscription, or a key is missing.")
    )
    return text, {
        "status": status,
        "provider": provider,
        "subscriptionId": sub_id,
        "eventCount": len(events),
        "events": events,
        "streamState": manager.state,
    }


def _default_stream_provider(symbols: list[str]) -> str:
    """Crypto-looking symbols → Binance; everything else → Finnhub (keyed)."""
    from .instruments import classify_identifier

    if symbols and all(classify_identifier(s)["kind"] == "crypto" for s in symbols):
        return "binance"
    return "finnhub"


def _render_stream(snapshot: Any) -> str:
    if isinstance(snapshot, dict) and "managers" in snapshot:
        snapshot = snapshot["managers"]
    if isinstance(snapshot, dict) and "metrics" not in snapshot and "state" not in snapshot:
        lines = [f"Stream providers: {', '.join(snapshot.keys()) or 'none'}"]
        for name, snap in snapshot.items():
            lines.append(f"  [{name}] state={snap.get('state')} subs={len(snap.get('subscriptions') or [])}")
        return "\n".join(lines)
    lines = [
        f"Stream state: {snapshot.get('state')} (provider {snapshot.get('provider')})",
        f"Subscriptions: {len(snapshot.get('subscriptions') or [])}",
    ]
    for sub in snapshot.get("subscriptions") or []:
        lines.append(f"  - {sub['id']}: {', '.join(sub['symbols'])} {sub['eventTypes']}")
    lines.append(f"Metrics: {json.dumps(snapshot.get('metrics') or {})}")
    return "\n".join(lines)


# ── Registration ────────────────────────────────────────────────────────────

async def backfill_history(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Fill the local vault: fetch history once and keep it.

    This is how a local-first runtime "bundles" data: the user decides which
    universe to hold, Eclipse fetches it once, and every later run is served
    from the machine - offline, fast and reproducible.
    """
    from .series_store import get_series_store

    gateway = getattr(ctx, "market_gateway", None)
    store = getattr(ctx, "market_series_store", None) or get_series_store()
    if gateway is None:
        return ("The market data layer is unavailable in this runtime.",
                {"status": "unavailable",
                 "reason": "the market data layer is unavailable"})
    if store is None:
        return ("The durable history cache is unavailable in this runtime.",
                {"status": "unavailable",
                 "reason": "the durable history cache is unavailable"})

    symbols = [str(s).strip() for s in (args.get("symbols") or []) if str(s).strip()]
    if not symbols:
        return ("Provide the `symbols` to bundle.",
                {"status": "error", "reason": "at least one symbol is required"})
    max_symbols = max(1, min(int(args.get("maxSymbols") or 25), 100))
    symbols = symbols[:max_symbols]
    interval = str(args.get("interval") or "1d")
    start = args.get("start")
    end = args.get("end")
    provider = args.get("provider")
    adjusted = bool(args.get("adjusted", True))

    # Which providers are usable RIGHT NOW, and which of them need a key. This
    # is the honest answer to "do I need a subscription to bundle data?": the
    # keyless providers (Yahoo, Stooq, Binance, ECB, Treasury/FRED) are enough
    # to hold a real universe, and the local vault keeps it.
    provider_states = _provider_states(gateway)

    added: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            before = store.coverage(symbol, interval, adjusted=adjusted)
            result = await gateway.get_historical_prices(
                symbol, None, start=start, end=end, interval=interval,
                adjusted=adjusted, provider=provider)
        except Exception as exc:  # noqa: BLE001 - one symbol must not stop the run
            failed.append({"symbol": symbol, "reason": str(exc)[:200]})
            continue
        if isinstance(result, str) or not hasattr(result, "bars"):
            failed.append({"symbol": symbol,
                           "reason": "the provider returned no series"})
            continue
        bars = list(getattr(result, "bars", []) or [])
        if not bars:
            failed.append({"symbol": symbol, "reason": "no bars in the window"})
            continue
        rows = [_bar_row(bar) for bar in bars]
        written = store.save_bars(symbol, interval,
                                   str(getattr(result, "provider", "") or "unknown"),
                                   adjusted, rows)
        after = store.coverage(symbol, interval, adjusted=adjusted)
        served_by = str(getattr(result, "provider", "") or "")
        state = provider_states.get(served_by, {})
        added.append({
            "symbol": symbol,
            "barsWritten": written,
            "barsHeld": after.get("barCount"),
            "start": after.get("start"),
            "end": after.get("end"),
            "wasHolding": before.get("barCount"),
            "provider": served_by,
            "needsCredential": bool(state.get("credentialRef")),
            "credentialConfigured": bool(state.get("configured")),
        })

    held = sum(int(a.get("barsHeld") or 0) for a in added)
    lines = [f"{a['symbol']}: {a['barsHeld']} bars held "
             f"({a['start']} ? {a['end']})" for a in added]
    keyless = sorted({a["provider"] for a in added
                       if a.get("provider") and not a.get("needsCredential")})
    if keyless:
        lines.append("bundled from keyless providers: " + ", ".join(keyless)
                     + " - no subscription, and the local vault keeps it")
    if failed:
        lines.append(f"{len(failed)} symbol(s) could not be bundled: "
                     + ", ".join(f"{f['symbol']}" for f in failed))
    if not lines:
        return ("Nothing could be bundled.", {"status": "error", "added": added,
                                             "failed": failed})
    return ("Bundled " + "; ".join(lines) + f" - {held} bars held locally.",
            {"status": "ok", "added": added, "failed": failed,
             "barsHeld": held, "count": len(added),
             "keylessProviders": keyless,
             "providers": provider_states})


def _provider_states(gateway: Any) -> dict[str, Any]:
    """What each provider needs, right now: a key, or nothing at all."""
    try:
        described = gateway._router_ref().describe()  # noqa: SLF001 - introspection seam
    except Exception:  # noqa: BLE001 - introspection is a nicety
        return {}
    out: dict[str, Any] = {}
    for provider in (described or {}).get("providers", []) or []:
        pid = str(provider.get("id") or "")
        if not pid:
            continue
        out[pid] = {
            "label": provider.get("label"),
            "credentialRef": provider.get("credentialRef"),
            "configured": provider.get("configured"),
            "historical": provider.get("historical"),
            "implemented": provider.get("implemented"),
        }
    return out


def _bar_row(bar: Any) -> dict[str, Any]:
    """A bar as the durable store wants it, whether it is a model or a dict."""
    if isinstance(bar, dict):
        return {k: bar.get(k) for k in
                ("timestamp", "open", "high", "low", "close", "volume", "vwap")}
    return {k: getattr(bar, k, None) for k in
            ("timestamp", "open", "high", "low", "close", "volume", "vwap")}


async def history_catalog(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """What history this machine already holds."""
    from .series_store import get_series_store

    store = getattr(ctx, "market_series_store", None) or get_series_store()
    if store is None:
        return ("The durable history cache is unavailable in this runtime.",
                {"status": "unavailable",
                 "reason": "the durable history cache is unavailable in this runtime"})
    symbol = str(args.get("symbol") or "").strip()
    interval = str(args.get("interval") or "1d")
    try:
        if symbol:
            coverage = store.coverage(symbol, interval)
            series = [coverage]
        else:
            series = store.list_series(limit=int(args.get("limit") or 100))
    except Exception as exc:  # noqa: BLE001 - a read failure is reported
        return (f"The history catalog could not be read: {exc}",
                {"status": "error", "reason": str(exc)[:200]})
    if not series:
        return ("This machine holds no cached history yet.",
                {"status": "ok", "series": [], "count": 0})
    lines = []
    for row in series:
        store = row.get("store") or "history_cache"
        if symbol:
            lines.append(f"{row.get('symbol')} {row.get('interval')}: "
                         f"{row.get('barCount')} bars, {row.get('start')} -> "
                         f"{row.get('end')} [store={store}]")
        else:
            lines.append(f"{row.get('symbol')} {row.get('interval')}: "
                         f"{row.get('barCount')} bars from {row.get('provider')}, "
                         f"{row.get('start')} -> {row.get('end')} [store={store}]")
    return ("\n".join(lines), {"status": "ok", "store": "history_cache",
                               "series": series, "count": len(series)})


def register_market_tools(registry: Any) -> None:
    """Register the eighteen market-data tools on the shared registry."""
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any], timeout: int) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=handler, permission="read", risk="low", timeout_ms=timeout,
        ))

    _def(
        "backfill_history",
        "Bundle history into the local vault: fetch the window once and keep it, so "
        "every later run is served from this machine - offline, fast and "
        "reproducible. This is how a local-first runtime holds a universe: the user "
        "decides what to keep, and the data becomes local. Reports what each symbol "
        "now holds and what could not be bundled.",
        backfill_history,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "interval": {"type": "string"},
            "start": {"type": "string"}, "end": {"type": "string"},
            "provider": {"type": "string"},
            "adjusted": {"type": "boolean"},
            "maxSymbols": {"type": "integer"}},
            "required": ["symbols"]},
        300_000,
    )
    _def(
        "history_catalog",
        "What provider-cached history this machine already holds (store="
        "history_cache): which instruments, how many bars, how fresh, and from "
        "which provider. This is the durable copy of bars fetched from providers; "
        "it is NOT the JDdS vault and its counts are not JDdS counts. With "
        "`symbol`, the coverage of that one instrument. Served from the local "
        "cache; no provider is called.",
        history_catalog,
        {"type": "object", "properties": {
            "symbol": {"type": "string"},
            "interval": {"type": "string"},
            "limit": {"type": "integer"}}, "required": []},
        20_000,
    )
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
        "get_tvl",
        "Get DeFi total value locked (TVL) for a protocol ticker (AAVE, UNI, LDO…) or a "
        "chain name (Ethereum, Solana, Arbitrum…). Per-chain breakdown is returned when "
        "the provider supplies it; an unknown identifier is UNAVAILABLE, never zero.",
        get_tvl,
        {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Protocol ticker or chain name."},
            "market": {"type": "string"},
            "chain": {"type": "string", "description": "Explicit chain when requesting chain TVL."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_onchain_metric",
        "Get account-scoped on-chain metrics for an EVM address (native balance, "
        "transaction count, latest block). Chain defaults to ethereum. Requires an "
        "Etherscan key; without one the result is an honest UNAVAILABLE.",
        get_onchain_metric,
        {"type": "object", "properties": {
            "address": {"type": "string", "description": "0x… EVM address."},
            "chain": {"type": "string", "description": "ethereum | arbitrum | optimism | polygon | base | bsc | avalanche."},
            "freshness": {"type": "string"},
        }, "required": ["address"]},
        15_000,
    )
    _def(
        "get_liquidations",
        "Get futures forced-liquidation totals for a coin on one exchange (1h/4h/12h/24h "
        "long vs short, USD). Requires a CoinGlass key; without one the result is an "
        "honest UNAVAILABLE, never a zero.",
        get_liquidations,
        {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Coin symbol, e.g. BTC."},
            "market": {"type": "string"},
            "exchange": {"type": "string", "description": "Futures exchange, default Binance."},
            "window": {"type": "string", "description": "Reported window (24h is the headline)."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
    )
    _def(
        "get_long_short_ratio",
        "Get the global long/short account ratio history for a futures pair (long %, "
        "short %, ratio, series). Requires a CoinGlass key; absent it is UNAVAILABLE.",
        get_long_short_ratio,
        {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Coin symbol, e.g. BTC (mapped to BTCUSDT)."},
            "market": {"type": "string"},
            "exchange": {"type": "string", "description": "Futures exchange, default Binance."},
            "interval": {"type": "string", "description": "1m,5m,15m,30m,1h,4h,12h,1d,1w."},
            "limit": {"type": "integer", "description": "Points to return (default 48, max 1000)."},
            "freshness": {"type": "string"},
        }, "required": ["symbol"]},
        15_000,
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
            "provider": {"type": "string",
                         "description": "Streaming provider: binance (crypto, keyless) or finnhub (equities, keyed). Auto-selected when omitted."},
            "count": {"type": "integer", "description": "Events to sample (default 5)."},
            "duration_seconds": {"type": "number", "description": "Sampling window (default 8s, max 20)."},
            "subscription_id": {"type": "string", "description": "For unsubscribe / reuse."},
        }},
        25_000,
    )


__all__ = ["register_market_tools"]
