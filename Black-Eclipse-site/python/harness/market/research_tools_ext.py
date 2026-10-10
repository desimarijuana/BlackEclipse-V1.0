"""Secondary research tools: calendar, FX conversion, corporate actions,
universe resolution, and dataset export/refresh.

Split out of `research_tools.py` to keep each module under the size budget. The
handlers reuse the shared helpers in `research_tools` (imported lazily to avoid a
module cycle); `_series_store` is defined here and re-exported by
`research_tools` because several core handlers need it.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import INVALID_REQUEST, MarketError


def _series_store(ctx: Any):
    from .series_store import SeriesStore

    cached = getattr(ctx, "_series_store", None)
    if cached is not None:
        return cached
    market_store = getattr(ctx, "market_store", None)
    if market_store is None:
        return None
    store = SeriesStore(market_store)
    try:
        ctx._series_store = store  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return store


async def get_trading_calendar(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    import datetime as _dt

    from .calendar import is_open, market_kind, next_session_open, us_holidays
    from .research_tools import _unavailable

    kind = str(args.get("market") or "").strip().lower()
    asset = args.get("asset_type")
    if kind in ("us_equity", "crypto", "fx"):
        resolved = kind
    else:
        resolved = market_kind(asset, args.get("market")) if (asset or kind) else "us_equity"
    if resolved not in ("us_equity", "crypto", "fx"):
        return _unavailable(f"unknown market '{kind}'", code="INVALID_REQUEST")
    now = _dt.datetime.now(_dt.timezone.utc)
    try:
        year = int(args.get("year") or now.year)
    except (TypeError, ValueError):
        year = now.year
    holidays = sorted(d.isoformat() for d in us_holidays(year)) if resolved == "us_equity" else []
    nxt = next_session_open(resolved, now)
    data = {
        "market": resolved, "year": year, "openNow": is_open(resolved, now),
        "now": now.isoformat(),
        "nextOpen": nxt.isoformat() if nxt else None,
        "holidays": holidays,
        "session": {"us_equity": "09:30–16:00 America/New_York",
                    "fx": "Sun 17:00 – Fri 17:00 ET", "crypto": "24/7"}.get(resolved),
    }
    return (
        f"CALENDAR {resolved} {year}: openNow={data['openNow']}, "
        f"nextOpen={data['nextOpen']}, {len(holidays)} holiday(s)",
        {"status": "OK", **data},
    )


async def get_currency_conversion(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .research_tools import _gateway, _unavailable

    base = str(args.get("base") or "").strip().upper()
    quote = str(args.get("quote") or "").strip().upper()
    if not base or not quote:
        return _unavailable("base and quote are required", code="INVALID_REQUEST")
    try:
        amount = float(args.get("amount") or 1.0)
    except (TypeError, ValueError):
        return _unavailable("amount must be a number", code="INVALID_REQUEST")
    gateway = _gateway(ctx)

    async def _rate(a: str, b: str) -> Optional[float]:
        result = await gateway.get_fx_rate(base=a, quote=b, freshness="daily")
        if isinstance(result, MarketError):
            return None
        return result.mid or result.rate

    rate = await _rate(base, quote)
    derived = False
    derivation = f"direct {base}/{quote}"
    if rate is None and base != "USD" and quote != "USD":
        r1 = await _rate(base, "USD")
        r2 = await _rate("USD", quote)
        if r1 and r2:
            rate = r1 * r2
            derived = True
            derivation = f"cross via USD: {base}/USD × USD/{quote}"
    if rate is None:
        return _unavailable(f"no FX rate for {base}/{quote}", code="DATA_NOT_AVAILABLE")
    converted = amount * rate
    return (
        f"{amount:.4f} {base} = {converted:.4f} {quote} (rate {rate:.6f}"
        + (", derived)" if derived else ")"),
        {"status": "OK", "base": base, "quote": quote, "amount": amount,
         "rate": rate, "converted": converted, "derived": derived, "derivation": derivation},
    )


async def get_corporate_actions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .research_tools import _fetch_series, _gateway, _parse_symbols, _unavailable

    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("at least one symbol is required", code="INVALID_REQUEST")
    interval = str(args.get("interval") or "1d")
    gateway = _gateway(ctx)
    out: list[dict[str, Any]] = []
    for symbol in symbols:
        series = await _fetch_series(
            gateway, symbol, interval=interval, start=args.get("start"),
            end=args.get("end"), adjusted=bool(args.get("adjusted", True)),
        )
        if isinstance(series, MarketError):
            out.append({"symbol": symbol, "status": "UNAVAILABLE", "error": series.to_dict()})
            continue
        actions = series.corporate_actions or []
        out.append({"symbol": symbol, "status": "OK" if actions else "UNAVAILABLE",
                    "actions": actions, "provider": series.meta.provider,
                    "note": None if actions else "provider supplied no corporate actions for this range"})
    any_ok = any(e.get("status") == "OK" for e in out)
    text = "CORPORATE ACTIONS — " + "; ".join(
        f"{e['symbol']}: {len(e.get('actions', []))}" if e.get("status") == "OK"
        else f"{e['symbol']}: unavailable" for e in out)
    return text, {"status": "OK" if any_ok else "UNAVAILABLE", "results": out}


async def get_universe(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .research_tools import _gateway, _parse_symbols, _unavailable

    symbols = _parse_symbols(args)
    watchlist = args.get("watchlist")
    if watchlist and isinstance(watchlist, list):
        symbols = [*symbols, *[str(s).upper() for s in watchlist]]
    symbols = list(dict.fromkeys(symbols))[:200]
    if not symbols:
        return _unavailable("symbols or watchlist is required", code="INVALID_REQUEST")
    as_of = args.get("as_of")
    gateway = _gateway(ctx)
    members: list[dict[str, Any]] = []
    for symbol in symbols:
        instrument, err = await gateway.resolve_instrument(symbol)
        if instrument is None or err is not None:
            members.append({"symbol": symbol, "resolved": False,
                            "reason": (err.message if err else "unresolved")})
            continue
        members.append({
            "symbol": symbol, "resolved": True, "instrumentId": instrument.instrument_id,
            "assetType": instrument.asset_type, "market": instrument.market,
            "exchange": instrument.exchange,
        })
    # Membership is resolved from CURRENT identities; historical membership is
    # unknown unless a source provides it. This is the survivorship-bias guard.
    as_of_unknown = bool(as_of)
    return (
        f"UNIVERSE — {sum(1 for m in members if m.get('resolved'))}/{len(members)} resolved"
        + (f" (asOf={as_of}: historical membership UNKNOWN)" if as_of_unknown else ""),
        {"status": "OK", "universeId": args.get("universe_id"), "asOf": as_of,
         "membershipBasis": "current_identities", "asOfUnknown": as_of_unknown,
         "count": len(members), "members": members},
    )


async def export_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    import csv
    import io
    import json as _json
    import os

    from .research_tools import _dataset_store, _unavailable

    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    if not dataset_id:
        return _unavailable("dataset_id is required", code="INVALID_REQUEST")
    version = args.get("version")
    fmt = str(args.get("format") or "csv").lower()
    if fmt not in ("csv", "json"):
        return _unavailable("format must be csv or json", code="INVALID_REQUEST")
    try:
        artifact = store.read_artifact(dataset_id, str(version) if version else None)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    series: dict[str, list[dict[str, Any]]] = artifact.get("series", {})
    selected = args.get("symbols")
    if selected:
        wanted = {str(s).upper() for s in selected}
        series = {k: v for k, v in series.items() if k.upper() in wanted}
    start, end, as_of = args.get("start"), args.get("end"), args.get("as_of")
    default_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                                ".black-eclipse", "quant", "exports"))
    out_dir = args.get("out_dir")
    root = os.path.abspath(str(out_dir)) if out_dir else default_root
    os.makedirs(root, exist_ok=True)
    written: list[str] = []
    total = 0
    pit_unknown = False
    for symbol, rows in series.items():
        kept = [r for r in rows
                if (not start or str(r.get("timestamp", "")) >= str(start))
                and (not end or str(r.get("timestamp", "")) <= str(end))]
        if as_of:
            filtered = []
            for r in kept:
                known = r.get("knownAt") or r.get("known_at")
                if known is None:
                    pit_unknown = True
                    filtered.append(r)
                elif str(known) <= str(as_of):
                    filtered.append(r)
            kept = filtered
        total += len(kept)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol)
        path = os.path.join(root, f"{dataset_id}__{version or 'latest'}__{safe}.{fmt}")
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(
                buf, fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
                extrasaction="ignore")
            writer.writeheader()
            for r in kept:
                writer.writerow(r)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(buf.getvalue())
        else:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"symbol": symbol, "rows": kept}, fh, default=str)
        written.append(path)
    return (
        f"EXPORT {dataset_id} {version or 'latest'} → {len(written)} file(s), {total} row(s)"
        + (" (PIT not enforceable)" if pit_unknown else ""),
        {"status": "OK", "datasetId": dataset_id, "version": version, "format": fmt,
         "files": written, "rowCount": total, "pitUnknown": pit_unknown},
    )


async def refresh_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .research_tools import _dataset_store, _fetch_series, _gateway, _parse_symbols, _series_to_rows, _unavailable

    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    if not dataset_id:
        return _unavailable("dataset_id is required", code="INVALID_REQUEST")
    try:
        prior = store.get_version(dataset_id, args.get("from_version"))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    req = prior.get("request") or {}
    symbols = _parse_symbols(args) or list(req.get("symbols") or [])
    if not symbols:
        return _unavailable("no symbols to refresh", code="INVALID_REQUEST")
    interval = str(args.get("interval") or req.get("interval") or "1d")
    start = args.get("start") if args.get("start") is not None else req.get("start")
    end = args.get("end") if args.get("end") is not None else req.get("end")
    adjusted = bool(args.get("adjusted", req.get("adjusted", True)))
    gateway = _gateway(ctx)
    series: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        fetched = await _fetch_series(gateway, symbol, interval=interval, start=start,
                                      end=end, adjusted=adjusted)
        if isinstance(fetched, MarketError):
            return _unavailable(f"{symbol}: {fetched.message}", code=fetched.code)
        series[symbol] = _series_to_rows(fetched)
    manifest = store.build_version(
        series=series, dataset_id=dataset_id,
        request={**req, "symbols": symbols, "interval": interval, "start": start,
                 "end": end, "adjusted": adjusted, "refreshed": True},
        name=prior.get("name"), quality=prior.get("quality"),
        lineage=prior.get("lineage"), created_by=args.get("created_by"), force=True,
    )
    diff = store.compare_versions(dataset_id, prior["version"], manifest["version"])
    return (
        f"REFRESH {dataset_id}: {prior['version']} → {manifest['version']} "
        f"(rowDelta={diff['rowCountDelta']}, sameContent={diff['sameContent']})",
        {"status": "OK", "manifest": manifest, "diff": diff},
    )


__all__ = [
    "export_dataset",
    "get_corporate_actions",
    "get_currency_conversion",
    "get_trading_calendar",
    "get_universe",
    "refresh_dataset",
]
