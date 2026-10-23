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

    async def _rate(a: str, b: str):
        result = await gateway.get_fx_rate(base=a, quote=b, freshness="daily")
        if isinstance(result, MarketError):
            return None, result
        return (result.mid or result.rate), result

    rate, direct = await _rate(base, quote)
    derived = False
    derivation = f"direct {base}/{quote}"
    source = direct
    if rate is None and base != "USD" and quote != "USD":
        r1, src1 = await _rate(base, "USD")
        r2, src2 = await _rate("USD", quote)
        if r1 and r2:
            rate = r1 * r2
            derived = True
            source = src1
            derivation = f"cross via USD: {base}/USD x USD/{quote}"
    if rate is None:
        # D3: the SAME named refusal the other FX entry points return.
        code = direct.code if isinstance(direct, MarketError) else "DATA_NOT_AVAILABLE"
        return _unavailable(f"no FX rate for {base}/{quote}", code=code)
    converted = amount * rate
    return (
        f"{amount:.4f} {base} = {converted:.4f} {quote} (rate {rate:.6f}"
        + (", derived)" if derived else ")"),
        {"status": "OK", "base": base, "quote": quote, "amount": amount,
         "rate": rate, "converted": converted, "derived": derived, "derivation": derivation,
         "timestamp": source.meta.event_time if source is not None else None,
         "asOf": source.meta.event_time if source is not None else None,
         "provider": source.meta.provider if source is not None else None,
         "qualityVerdict": "VALID",
         "envelope": {"value": rate, "unit": "rate", "currency": quote,
                      "provider": source.meta.provider if source is not None else None,
                      "observationTimestamp": source.meta.event_time if source is not None else None,
                      "retrievalTimestamp": source.meta.retrieved_at if source is not None else None,
                      "nativeCadence": "realtime", "qualityVerdict": "VALID",
                      "conflicts": [], "routesSkipped": [], "stale": False,
                      "reasonCode": None}},
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


def _universe_store(ctx: Any):
    from .universe_store import UniverseStore

    market_store = getattr(ctx, "market_store", None)
    if market_store is None:
        return None
    return UniverseStore(market_store)


async def get_universe(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    import datetime as _dt

    from .research_tools import _gateway, _parse_symbols, _unavailable

    universe_id = args.get("universe_id")
    as_of = args.get("as_of")
    store = _universe_store(ctx)
    basis = "current_identities"
    as_of_unknown = bool(as_of)
    dated: dict[str, Any] = {}

    symbols = _parse_symbols(args)
    watchlist = args.get("watchlist")
    if watchlist and isinstance(watchlist, list):
        symbols = [*symbols, *[str(s).upper() for s in watchlist]]

    # A recorded universe resolves membership from its effective-dated history.
    if universe_id and store is not None and store.has(str(universe_id)):
        cut = str(as_of) if as_of else _dt.date.today().isoformat()
        recorded = store.members_as_of(str(universe_id), cut)
        symbols = [m["symbol"] for m in recorded]
        dated = {m["symbol"]: m for m in recorded}
        basis = "recorded_membership"
        as_of_unknown = False

    symbols = list(dict.fromkeys([s for s in symbols if s]))[:200]
    if not symbols:
        return _unavailable("symbols, watchlist or a recorded universe_id is required",
                            code="INVALID_REQUEST")
    gateway = _gateway(ctx)
    members: list[dict[str, Any]] = []
    for symbol in symbols:
        instrument, err = await gateway.resolve_instrument(symbol)
        entry: dict[str, Any] = {"symbol": symbol}
        if symbol in dated:
            entry["effectiveFrom"] = dated[symbol].get("effectiveFrom")
            entry["effectiveTo"] = dated[symbol].get("effectiveTo")
        if instrument is None or err is not None:
            entry.update({"resolved": False, "reason": (err.message if err else "unresolved")})
        else:
            entry.update({
                "resolved": True, "instrumentId": instrument.instrument_id,
                "assetType": instrument.asset_type, "market": instrument.market,
                "exchange": instrument.exchange,
            })
        members.append(entry)
    return (
        f"UNIVERSE — {sum(1 for m in members if m.get('resolved'))}/{len(members)} resolved "
        f"(basis={basis})"
        + (f" (asOf={as_of}: historical membership UNKNOWN)" if as_of_unknown else ""),
        {"status": "OK", "universeId": universe_id, "asOf": as_of,
         "membershipBasis": basis, "asOfUnknown": as_of_unknown,
         "count": len(members), "members": members},
    )


async def record_universe(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .research_tools import _parse_symbols, _unavailable

    store = _universe_store(ctx)
    if store is None:
        return _unavailable("universe store is not available")
    universe_id = str(args.get("universe_id") or "").strip()
    if not universe_id:
        return _unavailable("universe_id is required", code="INVALID_REQUEST")
    effective_from = args.get("effective_from") or args.get("as_of")
    if not effective_from:
        return _unavailable("effective_from (or as_of) is required", code="INVALID_REQUEST")
    raw = args.get("members")
    members: list[dict[str, Any]] = []
    if isinstance(raw, list) and raw:
        for m in raw:
            if isinstance(m, dict):
                members.append({
                    "symbol": m.get("symbol"),
                    "effectiveFrom": m.get("effectiveFrom") or m.get("effective_from") or effective_from,
                    "effectiveTo": m.get("effectiveTo") or m.get("effective_to"),
                    "meta": m.get("meta"),
                })
            elif isinstance(m, str):
                members.append({"symbol": m, "effectiveFrom": effective_from})
    else:
        members = [{"symbol": s, "effectiveFrom": effective_from}
                   for s in _parse_symbols(args)]
    recorded = store.record_membership(universe_id, members, name=args.get("name"))
    if recorded == 0:
        return _unavailable("no valid members to record", code="INVALID_REQUEST")
    return (
        f"UNIVERSE {universe_id}: recorded {recorded} membership row(s) effective {effective_from}",
        {"status": "OK", "universeId": universe_id, "recorded": recorded,
         "effectiveFrom": effective_from},
    )


def _returns(closes: list[float]) -> list[float]:
    out = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev:
            out.append(closes[i] / prev - 1)
    return out


def _stdev(xs: list[float]) -> float:
    import math

    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


async def analyze_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Run deterministic analytics over an immutable dataset version.

    Declarative operations only (no arbitrary code, no provider/secret access):
    `summary`, `returns`, `volatility`, `max_drawdown`, `sharpe`, `correlation`.
    """
    import math

    from .research_tools import _dataset_store, _unavailable

    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    if not dataset_id:
        return _unavailable("dataset_id is required", code="INVALID_REQUEST")
    try:
        artifact = store.read_artifact(dataset_id, str(args.get("version")) if args.get("version") else None)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    series: dict[str, list[dict[str, Any]]] = artifact.get("series", {})
    selected = args.get("symbols")
    if selected:
        wanted = {str(s).upper() for s in selected}
        series = {k: v for k, v in series.items() if k.upper() in wanted}
    if not series:
        return _unavailable("no series to analyze", code="DATA_NOT_AVAILABLE")
    operations = args.get("operations") or ["summary"]
    operations = [str(op) for op in operations]
    rf = float(args.get("risk_free_rate") or 0.0)
    periods = int(args.get("periods_per_year") or 252)

    closes: dict[str, list[float]] = {}
    for symbol, rows in series.items():
        closes[symbol] = [float(r["close"]) for r in rows if r.get("close") is not None]

    results: dict[str, Any] = {}
    for name in operations:
        symbol = args.get("symbol")
        if name == "summary":
            results["summary"] = {
                s: {"count": len(v), "first": v[0] if v else None, "last": v[-1] if v else None,
                    "mean": (sum(v) / len(v)) if v else None}
                for s, v in closes.items()
            }
        elif name == "returns":
            target = symbol or next(iter(closes))
            r = _returns(closes.get(target, []))
            results.setdefault("returns", {})[target] = {
                "count": len(r), "total": (math.prod(1 + x for x in r) - 1) if r else 0.0,
                "mean": (sum(r) / len(r)) if r else None,
            }
        elif name == "volatility":
            target = symbol or next(iter(closes))
            r = _returns(closes.get(target, []))
            results.setdefault("volatility", {})[target] = {
                "periodVol": _stdev(r), "annualized": _stdev(r) * math.sqrt(periods),
            }
        elif name == "max_drawdown":
            target = symbol or next(iter(closes))
            peak = None
            mdd = 0.0
            for price in closes.get(target, []):
                peak = price if peak is None else max(peak, price)
                if peak:
                    mdd = min(mdd, price / peak - 1)
            results.setdefault("max_drawdown", {})[target] = mdd
        elif name == "sharpe":
            target = symbol or next(iter(closes))
            r = _returns(closes.get(target, []))
            sd = _stdev(r)
            excess = (sum(r) / len(r) - rf / periods) if r else 0.0
            results.setdefault("sharpe", {})[target] = (excess / sd * math.sqrt(periods)) if sd else None
        elif name == "correlation":
            a, b = (symbol.split(",") + [None])[:2] if symbol else (None, None)
            keys = list(closes)
            if not a or not b:
                a, b = keys[0], keys[1] if len(keys) > 1 else None
            if b and a in closes and b in closes:
                map_a = {row["timestamp"]: row["close"] for row in series[a] if row.get("close") is not None}
                map_b = {row["timestamp"]: row["close"] for row in series[b] if row.get("close") is not None}
                common = sorted(set(map_a) & set(map_b))
                ra = _returns([map_a[t] for t in common])
                rb = _returns([map_b[t] for t in common])
                if len(ra) >= 2 and len(ra) == len(rb):
                    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
                    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (len(ra) - 1)
                    sa, sb = _stdev(ra), _stdev(rb)
                    results.setdefault("correlation", {})[f"{a},{b}"] = (cov / (sa * sb)) if (sa and sb) else None
        else:
            results.setdefault("errors", []).append(f"unknown operation {name!r}")
    return (
        f"ANALYZE {dataset_id} — {len(operations)} operation(s) over {len(closes)} symbol(s)",
        {"status": "OK", "datasetId": dataset_id, "version": args.get("version"),
         "operations": operations, "results": results},
    )


async def list_universes(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    store = _universe_store(ctx)
    if store is None:
        return _unavailable("universe store is not available")
    rows = store.list_universes()
    return (f"UNIVERSES — {len(rows)} recorded",
            {"status": "OK", "universes": rows})


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

