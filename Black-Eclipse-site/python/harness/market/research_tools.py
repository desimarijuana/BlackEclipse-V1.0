"""Shared quantitative-research tool surface.

These tools are the reusable research data API the directive requires: they sit
ON TOP of the Market Data Gateway (routing/quality/provenance), the verification
engine (`market/verification.py`), the deterministic transforms
(`quant/transform.py`) and the immutable dataset store (`quant/dataset_store.py`).

Every handler routes through shared services — none of them re-implements
provider fetching, verification or dataset storage. Every result carries
provenance and an explicit status; a failure is never a fabricated value.

Registered by `register_research_data_tools`; the exported `RESEARCH_DATA_TOOLS`
tuple is spread into agent allowlists so the tools are reachable by agents.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import INVALID_REQUEST, MarketError
from .gateway import MarketDataGateway
from .models import HistoricalPriceSeries
from .quality import evaluate
from .tools import _collect, _persist
from .research_tools_ext import (  # noqa: F401 - re-exported handlers
    analyze_dataset,
    export_dataset,
    get_corporate_actions,
    get_currency_conversion,
    get_trading_calendar,
    get_universe,
    list_universes,
    record_universe,
    refresh_dataset,
)
from .research_tools_ext import _series_store  # noqa: F401 - used by core handlers
from .verification import policy_names, resolve_policy, verify_series

_SERIES_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _gateway(ctx: Any) -> MarketDataGateway:
    gateway = getattr(ctx, "market_gateway", None)
    if gateway is not None:
        return gateway
    gateway = MarketDataGateway(getattr(ctx, "data_bridge", None))
    try:
        ctx.market_gateway = gateway  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - context may be frozen in tests
        pass
    return gateway


def _series_to_rows(series: HistoricalPriceSeries) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": bar.timestamp,
            "open": bar.open, "high": bar.high, "low": bar.low,
            "close": bar.close, "volume": bar.volume,
        }
        for bar in series.bars
    ]


def _parse_symbols(args: dict[str, Any]) -> list[str]:
    raw = args.get("symbols") or ([args["symbol"]] if args.get("symbol") else [])
    return [str(s).strip().upper() for s in raw if str(s).strip()]


async def _fetch_series(
    gateway: MarketDataGateway, symbol: str, *, interval: str,
    start: Optional[str], end: Optional[str], adjusted: bool,
    provider: Optional[str] = None,
) -> HistoricalPriceSeries | MarketError:
    return await gateway.get_historical_prices(
        symbol, None, start=start, end=end, interval=interval,
        adjusted=adjusted, provider=provider,
    )


def _unavailable(message: str, code: str = "DATA_NOT_AVAILABLE", **extra: Any) -> tuple[str, dict]:
    payload = {"status": "UNAVAILABLE", "error": {"code": code, "message": message}}
    payload.update(extra)
    return f"UNAVAILABLE — {code}: {message}", payload


def _error_text(err: MarketError) -> str:
    return f"UNAVAILABLE — {err.code}: {err.message}"


def _policy(args: dict[str, Any], key: str = "verification_policy"):
    name = args.get(key) or args.get("policy") or "fresh_preferred"
    try:
        return resolve_policy(str(name)), None
    except ValueError as exc:
        return None, MarketError(INVALID_REQUEST, str(exc), capability="verification")


# ── Handlers: introspection ──────────────────────────────────────────────────


async def resolve_instrument(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    gateway = _gateway(ctx)
    instrument, err = await gateway.resolve_instrument(
        str(args.get("symbol", "")), args.get("market")
    )
    if err is not None:
        return _error_text(err), {"status": "UNAVAILABLE", "error": err.to_dict()}
    assert instrument is not None
    data = {
        "instrumentId": instrument.instrument_id,
        "symbol": instrument.symbol,
        "assetType": instrument.asset_type,
        "market": instrument.market,
        "exchange": instrument.exchange,
        "currency": instrument.currency,
        "name": instrument.name,
        "providerSymbols": instrument.provider_symbols,
        "bridgeResolved": getattr(instrument, "bridge_resolved", False),
        "mappingConfidence": 1.0 if getattr(instrument, "bridge_resolved", False) else 0.6,
    }
    text = (
        f"{instrument.symbol} → {instrument.asset_type} {instrument.name or ''} "
        f"(id={instrument.instrument_id}, market={instrument.market or '?'})"
    )
    return text, {"status": "OK", "instrument": data}


async def list_providers(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    gateway = _gateway(ctx)
    router = gateway._router_ref()  # noqa: SLF001 - same-package introspection
    descriptors = [p.to_dict() for p in router.all()] if router else []
    lines = [f"{len(descriptors)} provider(s):"]
    for p in descriptors:
        lines.append(
            f"  [{p['id']}] {p['label']} — caps={','.join(p['capabilities'])} "
            f"timeliness={p['timeliness']} implemented={p['implemented']} "
            f"configured={p['configured']}"
        )
    return "\n".join(lines), {"status": "OK", "providers": descriptors}


async def get_provider_health(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    gateway = _gateway(ctx)
    router = gateway._router_ref()  # noqa: SLF001
    health = router.health_snapshot() if router else []
    metrics = gateway.provider_metrics()
    store = getattr(ctx, "market_store", None)
    durable = store.provider_health() if store is not None else []
    lines = ["Provider health:"]
    for h in health:
        breaker = h.get("breaker", {})
        lines.append(
            f"  [{h['provider']}] successes={h['successes']} failures={h['failures']} "
            f"breaker={breaker.get('state')}"
        )
    return "\n".join(lines), {
        "status": "OK", "health": health, "metrics": metrics, "durable": durable,
    }


# ── Handlers: retrieval + verification ───────────────────────────────────────


async def get_market_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("at least one symbol is required", code="INVALID_REQUEST")
    interval = str(args.get("interval") or "1d")
    if interval not in _SERIES_INTERVALS:
        return _unavailable(f"unsupported interval {interval!r}", code="INVALID_INTERVAL")
    start, end = args.get("start"), args.get("end")
    adjusted = bool(args.get("adjusted", True))
    provider = args.get("provider")
    spec, perr = _policy(args)
    if perr is not None:
        return _error_text(perr), {"status": "UNAVAILABLE", "error": perr.to_dict()}
    assert spec is not None
    gateway = _gateway(ctx)
    max_bars = max(1, min(int(args.get("max_bars") or 500), 5000))

    results: list[dict[str, Any]] = []
    verified_any = False
    for symbol in symbols:
        series = await _fetch_series(
            gateway, symbol, interval=interval, start=start, end=end,
            adjusted=adjusted, provider=provider,
        )
        if isinstance(series, MarketError):
            results.append({"symbol": symbol, "status": "UNAVAILABLE", "error": series.to_dict()})
            continue
        # Feed the Evidence & Research Engine + durable snapshot store, exactly as
        # the single-capability market tools do.
        _collect(ctx, series, "historical")
        _persist(ctx, series, "historical")
        rows = _series_to_rows(series)
        series_store = _series_store(ctx)
        if series_store is not None:
            try:
                series_store.save_bars(symbol, interval, series.meta.provider or "unknown",
                                       adjusted, rows)
            except Exception:  # noqa: BLE001 - persistence is best-effort
                pass
        entry: dict[str, Any] = {
            "symbol": symbol,
            "status": series.meta.data_status,
            "provider": series.meta.provider,
            "eventTime": series.meta.event_time,
            "retrievedAt": series.meta.retrieved_at,
            "quality": series.meta.quality,
            "warnings": series.meta.warnings,
            "barCount": len(rows),
            "rows": rows[-max_bars:],
        }
        if spec.require_verification:
            instrument, err = await gateway.resolve_instrument(symbol)
            if instrument is not None and err is None:
                verification = await _verify_symbol(
                    gateway, instrument, interval, start, end, adjusted,
                    spec=spec, tolerance=float(args.get("tolerance") or 0.015),
                    primary_provider=series.meta.provider,
                    primary_rows=rows,
                )
                entry["verification"] = verification
                verified_any = verified_any or bool(verification.get("verified"))
        results.append(entry)

    text = _render_market_data(results, interval, start, end, spec.name)
    status = "OK" if any(r.get("status") == "OK" for r in results) else "UNAVAILABLE"
    return text, {
        "status": status,
        "policy": spec.name,
        "verifiedAny": verified_any,
        "interval": interval,
        "start": start,
        "end": end,
        "results": results,
    }


async def _verify_symbol(
    gateway: MarketDataGateway, instrument: Any, interval: str,
    start: Optional[str], end: Optional[str], adjusted: bool, *,
    spec: Any, tolerance: float,
    primary_provider: Optional[str], primary_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fetch an independent second source and verify the primary against it."""
    order = gateway.candidate_providers("historical", instrument)
    alternate = next(
        (p for p in order if p != primary_provider and p not in (None, "")), None
    )
    if alternate is None:
        return {
            "policy": spec.name, "status": "unverified", "verified": False,
            "message": "no independent provider available for this instrument",
        }
    alt = await _fetch_series(
        gateway, instrument.symbol, interval=interval, start=start, end=end,
        adjusted=adjusted, provider=alternate,
    )
    if isinstance(alt, MarketError):
        return {
            "policy": spec.name, "status": "unverified", "verified": False,
            "message": f"independent source '{alternate}' unavailable: {alt.code}",
        }
    series_by_provider = {
        primary_provider or "primary": [
            (row["timestamp"], row["close"]) for row in primary_rows if row["close"] is not None
        ],
        alternate: [
            (bar.timestamp, bar.close) for bar in alt.bars if bar.close is not None
        ],
    }
    return verify_series(
        series_by_provider, capability="historical", policy=spec, tolerance=tolerance
    ).to_dict()


def _render_market_data(rows: list[dict[str, Any]], interval: str, start: Any, end: Any, policy: str) -> str:
    lines = [f"MARKET DATA ({interval}, {start or '…'} → {end or '…'}, policy={policy})"]
    for entry in rows:
        if entry.get("status") == "UNAVAILABLE":
            lines.append(f"  {entry['symbol']}: UNAVAILABLE ({entry['error'].get('code')})")
            continue
        verification = entry.get("verification")
        vtext = ""
        if verification:
            vtext = f" | verification={verification.get('status')}"
        lines.append(
            f"  {entry['symbol']}: {entry['barCount']} bar(s) from {entry.get('provider') or '?'}"
            f" (quality={entry.get('quality')}){vtext}"
        )
        # The model-visible text is the answer's only view of the data; a bar
        # COUNT alone hid the actual series (observed: "11,551 bars, no rows").
        # Show a bounded tail inline and say exactly how much `rows` carries.
        bars = entry.get("rows") or []
        if bars:
            lines.append(
                f"      latest {min(3, len(bars))} of {entry['barCount']} bar(s); "
                f"structured `rows` carries the last {len(bars)}:"
            )
            for bar in bars[-3:]:
                lines.append(
                    f"        {bar.get('timestamp')} O={bar.get('open')} H={bar.get('high')} "
                    f"L={bar.get('low')} C={bar.get('close')} V={bar.get('volume')}"
                )
    return "\n".join(lines)


async def verify_market_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("at least one symbol is required", code="INVALID_REQUEST")
    interval = str(args.get("interval") or "1d")
    start, end = args.get("start"), args.get("end")
    adjusted = bool(args.get("adjusted", True))
    tolerance = float(args.get("tolerance") or 0.015)
    spec, perr = _policy(args, key="policy")
    if perr is not None:
        return _error_text(perr), {"status": "UNAVAILABLE", "error": perr.to_dict()}
    assert spec is not None
    requested_providers = [str(p).lower() for p in (args.get("providers") or [])]
    gateway = _gateway(ctx)
    store = getattr(ctx, "market_store", None)

    outcomes: list[dict[str, Any]] = []
    for symbol in symbols:
        instrument, err = await gateway.resolve_instrument(symbol)
        if instrument is None or err is not None:
            outcomes.append({"symbol": symbol, "status": "failed",
                             "message": (err.message if err else "unresolved")})
            continue
        order = requested_providers or list(gateway.candidate_providers("historical", instrument))[:2]
        series_by_provider: dict[str, list[tuple[str, float]]] = {}
        for provider in order:
            fetched = await _fetch_series(
                gateway, symbol, interval=interval, start=start, end=end,
                adjusted=adjusted, provider=provider,
            )
            if isinstance(fetched, MarketError):
                continue
            series_by_provider[provider] = [
                (b.timestamp, b.close) for b in fetched.bars if b.close is not None
            ]
        outcome = verify_series(
            series_by_provider, capability="historical", policy=spec, tolerance=tolerance
        ).to_dict()
        outcome["symbol"] = symbol
        if store is not None and outcome.get("conflicts"):
            try:
                store.record_quality(
                    "historical", symbol, None,
                    findings=[{"kind": "conflict", "severity": "warning",
                               "detail": outcome.get("message")}],
                    conflict=outcome["conflicts"][0],
                )
            except Exception:  # noqa: BLE001 - persistence best-effort
                pass
        outcomes.append(outcome)

    text_lines = [f"VERIFY MARKET DATA (policy={spec.name}, tolerance={tolerance:.1%})"]
    for o in outcomes:
        text_lines.append(f"  {o.get('symbol')}: {o.get('status')} — {o.get('message')}")
    return "\n".join(text_lines), {
        "status": "OK", "policy": spec.name, "tolerance": tolerance, "outcomes": outcomes,
    }


async def resample_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from ..quant.transform import TransformError, resample_rows

    target = str(args.get("target_interval") or args.get("targetInterval") or "")
    source = str(args.get("interval") or args.get("source_interval") or "") or None
    if not target:
        return _unavailable("target_interval is required", code="INVALID_REQUEST")

    inline = args.get("rows")
    if inline:
        if not isinstance(inline, list):
            return _unavailable("rows must be a list", code="INVALID_REQUEST")
        try:
            result = resample_rows(inline, target, source_interval=source)
        except TransformError as exc:
            return _unavailable(str(exc), code="INVALID_INTERVAL")
        return _render_resample({"?": result}, "inline"), {"status": "OK", "results": {"?": result}}

    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("symbols or rows are required", code="INVALID_REQUEST")
    gateway = _gateway(ctx)
    results: dict[str, Any] = {}
    for symbol in symbols:
        series = await _fetch_series(
            gateway, symbol, interval=source or "1d", start=args.get("start"),
            end=args.get("end"), adjusted=bool(args.get("adjusted", True)),
            provider=args.get("provider"),
        )
        if isinstance(series, MarketError):
            results[symbol] = {"status": "UNAVAILABLE", "error": series.to_dict()}
            continue
        try:
            results[symbol] = resample_rows(_series_to_rows(series), target, source_interval=source)
        except TransformError as exc:
            results[symbol] = {"status": "UNAVAILABLE", "error": {"code": "INVALID_INTERVAL", "message": str(exc)}}
    return _render_resample(results, target), {"status": "OK", "targetInterval": target, "results": results}


def _render_resample(results: dict[str, Any], target: str) -> str:
    lines = [f"RESAMPLE → {target}"]
    for symbol, res in results.items():
        if isinstance(res, dict) and res.get("status") == "UNAVAILABLE":
            lines.append(f"  {symbol}: UNAVAILABLE")
            continue
        meta = res.get("metadata", {})
        lines.append(
            f"  {symbol}: {meta.get('outputBars')} bar(s), "
            f"{meta.get('partialBuckets')} partial ({meta.get('aggregation')})"
        )
    return "\n".join(lines)


async def align_timeseries(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from ..quant.transform import TransformError, align_rows

    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("at least one symbol is required", code="INVALID_REQUEST")
    interval = str(args.get("interval") or "1d")
    gateway = _gateway(ctx)
    series: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        fetched = await _fetch_series(
            gateway, symbol, interval=interval, start=args.get("start"),
            end=args.get("end"), adjusted=bool(args.get("adjusted", True)),
            provider=args.get("provider"),
        )
        if isinstance(fetched, MarketError):
            return _unavailable(f"{symbol}: {fetched.message}", code=fetched.code)
        series[symbol] = _series_to_rows(fetched)
    try:
        aligned = align_rows(
            series, join=str(args.get("join") or "inner"),
            column=str(args.get("column") or "close"), fill=args.get("fill"),
        )
    except TransformError as exc:
        return _unavailable(str(exc), code="INVALID_REQUEST")
    max_points = max(1, min(int(args.get("max_points") or 500), 5000))
    timestamps = aligned["timestamps"]
    trimmed = {
        **aligned,
        "timestamps": timestamps[-max_points:],
        "series": {s: vals[-max_points:] for s, vals in aligned["series"].items()},
    }
    lines = [
        f"ALIGN ({aligned['join']}, column={aligned['column']}) — "
        f"{len(timestamps)} timestamp(s) across {len(symbols)} symbol(s)"
    ]
    for symbol, miss in aligned["missing"].items():
        lines.append(f"  {symbol}: {miss} missing value(s)")
    return "\n".join(lines), {"status": "OK", **trimmed}


# ── Handlers: datasets ───────────────────────────────────────────────────────


def _dataset_store(ctx: Any):
    return getattr(ctx, "dataset_store", None)


async def build_research_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    symbols = _parse_symbols(args)
    if not symbols:
        return _unavailable("at least one symbol is required", code="INVALID_REQUEST")
    interval = str(args.get("interval") or "1d")
    start, end = args.get("start"), args.get("end")
    adjusted = bool(args.get("adjusted", True))
    spec, perr = _policy(args)
    if perr is not None:
        return _error_text(perr), {"status": "UNAVAILABLE", "error": perr.to_dict()}
    assert spec is not None
    gateway = _gateway(ctx)

    series: dict[str, list[dict[str, Any]]] = {}
    quality: dict[str, Any] = {}
    lineage: dict[str, Any] = {}
    for symbol in symbols:
        fetched = await _fetch_series(
            gateway, symbol, interval=interval, start=start, end=end, adjusted=adjusted,
            provider=args.get("provider"),
        )
        if isinstance(fetched, MarketError):
            return _unavailable(f"{symbol}: {fetched.message}", code=fetched.code)
        rows = _series_to_rows(fetched)
        series[symbol] = rows
        series_store = _series_store(ctx)
        if series_store is not None:
            try:
                series_store.save_bars(symbol, interval, fetched.meta.provider or "unknown",
                                       adjusted, rows)
            except Exception:  # noqa: BLE001
                pass
        report = evaluate(fetched, "historical")
        quality[symbol] = {
            "status": report.status, "findings": [f.to_dict() for f in report.findings],
            "provider": fetched.meta.provider, "eventTime": fetched.meta.event_time,
            "retrievedAt": fetched.meta.retrieved_at,
        }
        lineage[symbol] = {
            "provider": fetched.meta.provider,
            "source": fetched.meta.source,
            "observationSource": fetched.meta.observation_source,
        }
        if spec.require_verification:
            instrument, err = await gateway.resolve_instrument(symbol)
            if instrument is not None and err is None:
                lineage[symbol]["verification"] = await _verify_symbol(
                    gateway, instrument, interval, start, end, adjusted, spec=spec,
                    tolerance=float(args.get("tolerance") or 0.015),
                    primary_provider=fetched.meta.provider, primary_rows=rows,
                )

    try:
        manifest = store.build_version(
            series=series,
            request={
                "symbols": symbols, "interval": interval, "start": start, "end": end,
                "adjusted": adjusted, "verificationPolicy": spec.name,
            },
            name=args.get("name"), dataset_id=args.get("dataset_id"),
            quality=quality, lineage=lineage, created_by=args.get("created_by"),
            force=bool(args.get("force", False)),
        )
    except Exception as exc:  # noqa: BLE001 - surface as a structured failure
        return _unavailable(str(exc), code="DATASET_BUILD_FAILED")
    _register_dataset_artifact(ctx, manifest)
    cov = manifest.get("coverage", {})
    text = (
        f"DATASET {manifest['datasetId']} {manifest['version']} "
        f"({'created' if manifest.get('created', True) else 'existing'}) — "
        f"{cov.get('symbolCount')} symbol(s), {cov.get('rowCount')} row(s), "
        f"hash={manifest['contentHash'][:12]}…"
    )
    return text, {"status": "OK", "manifest": manifest}


def _register_dataset_artifact(ctx: Any, manifest: dict[str, Any]) -> None:
    """Catalogue a built dataset in the Artifact Center (best-effort linkage).

    Registers the manifest itself (bounded JSON) with a stable idempotency key so
    a rebuild does not create duplicates, and links it to the run. Guarded: a
    missing/foreign artifact service must never fail a dataset build.
    """
    service = getattr(ctx, "artifact_service", None)
    if service is None:
        return
    try:
        import json as _json

        blob = _json.dumps(manifest, default=str).encode("utf-8")
        service.register_bytes(
            blob,
            name=f"research-dataset {manifest.get('datasetId')} {manifest.get('version')}",
            source_tool="build_research_dataset",
            run_id=getattr(ctx, "run_id", None),
            idempotency_key=f"research-dataset:{manifest.get('datasetId')}:{manifest.get('version')}",
            tags=["research-dataset", "quant"],
            metadata={"datasetId": manifest.get("datasetId"), "version": manifest.get("version"),
                      "contentHash": manifest.get("contentHash")},
        )
    except Exception:  # noqa: BLE001 - linkage is optional
        pass


async def get_dataset_versions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    if not dataset_id:
        return _unavailable("dataset_id is required", code="INVALID_REQUEST")
    try:
        versions = store.list_versions(dataset_id)
        latest = store.get_version(dataset_id)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    lines = [f"DATASET {dataset_id} — {len(versions)} version(s); latest {latest['version']}"]
    for v in versions:
        lines.append(f"  {v['version']} hash={v['contentHash'][:12]}… created={v['createdAt']}")
    return "\n".join(lines), {"status": "OK", "datasetId": dataset_id,
                              "versions": versions, "latest": latest}


async def compare_datasets(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    a, b = args.get("version_a"), args.get("version_b")
    if not dataset_id or not a or not b:
        return _unavailable("dataset_id, version_a and version_b are required",
                            code="INVALID_REQUEST")
    try:
        diff = store.compare_versions(dataset_id, str(a), str(b))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    text = (
        f"COMPARE {dataset_id} {a}→{b}: sameContent={diff['sameContent']}, "
        f"rowDelta={diff['rowCountDelta']}, added={diff['addedSymbols']}, "
        f"removed={diff['removedSymbols']}"
    )
    return text, {"status": "OK", "diff": diff}


async def query_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    store = _dataset_store(ctx)
    if store is None:
        return _unavailable("dataset store is not available")
    dataset_id = str(args.get("dataset_id") or "")
    version = args.get("version")
    if not dataset_id:
        return _unavailable("dataset_id is required", code="INVALID_REQUEST")
    try:
        artifact = store.read_artifact(dataset_id, str(version) if version else None)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(str(exc), code="DATASET_NOT_FOUND")
    series: dict[str, list[dict[str, Any]]] = artifact.get("series", {})
    selected = args.get("symbols")
    if selected:
        wanted = {str(s).upper() for s in selected}
        series = {k: v for k, v in series.items() if k.upper() in wanted}
    start, end = args.get("start"), args.get("end")
    as_of = args.get("as_of")
    limit = max(1, min(int(args.get("limit") or 200), 5000))
    out: dict[str, list[dict[str, Any]]] = {}
    pit_unknown = False
    for symbol, rows in series.items():
        filtered = [
            r for r in rows
            if (not start or str(r.get("timestamp", "")) >= str(start))
            and (not end or str(r.get("timestamp", "")) <= str(end))
        ]
        if as_of:
            kept = []
            for r in filtered:
                known = r.get("knownAt") or r.get("known_at")
                if known is None:
                    pit_unknown = True
                    kept.append(r)  # keep, but flag that PIT could not be enforced
                elif str(known) <= str(as_of):
                    kept.append(r)
            filtered = kept
        out[symbol] = filtered[-limit:]
    total = sum(len(v) for v in out.values())
    return (
        f"DATASET {dataset_id}{(' ' + str(version)) if version else ''} — "
        f"{len(out)} symbol(s), {total} row(s) projected"
        + (" (PIT not enforceable: rows carry no known-at metadata)" if pit_unknown else ""),
        {"status": "OK", "datasetId": dataset_id, "version": version, "series": out,
         "asOf": as_of, "pitUnknown": pit_unknown},
    )


async def get_data_quality_report(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    dataset_id = args.get("dataset_id")
    store = _dataset_store(ctx)
    if dataset_id and store is not None:
        try:
            manifest = store.get_version(str(dataset_id), args.get("version"))
        except Exception as exc:  # noqa: BLE001
            return _unavailable(str(exc), code="DATASET_NOT_FOUND")
        return (
            f"QUALITY {dataset_id} {manifest['version']} — "
            f"{len(manifest.get('quality', {}))} symbol report(s)",
            {"status": "OK", "scope": "dataset", "quality": manifest.get("quality", {}),
             "coverage": manifest.get("coverage", {})},
        )
    market_store = getattr(ctx, "market_store", None)
    if market_store is None:
        return _unavailable("no quality source is available")
    symbol = str(args.get("symbol") or "").upper() or None
    events = market_store.recent_quality(limit=int(args.get("limit") or 50))
    if symbol:
        events = [e for e in events if (e.get("symbol") or "").upper() == symbol]
    stored: list[dict[str, Any]] = []
    ss = _series_store(ctx)
    if ss is not None:
        try:
            stored = ss.list_series()
        except Exception:  # noqa: BLE001
            stored = []
    return (
        f"QUALITY — {len(events)} recent finding(s)" + (f" for {symbol}" if symbol else "")
        + f"; {len(stored)} stored series",
        {"status": "OK", "scope": "market", "events": events, "storedSeries": stored},
    )


async def get_data_provenance(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    symbol = str(args.get("symbol") or "").upper()
    capability = str(args.get("capability") or "quote")
    if not symbol:
        return _unavailable("symbol is required", code="INVALID_REQUEST")
    market_store = getattr(ctx, "market_store", None)
    snapshot = market_store.get_snapshot(capability, symbol) if market_store else None
    if snapshot is None:
        return _unavailable(f"no stored {capability} provenance for {symbol}",
                            code="DATA_NOT_AVAILABLE")
    payload = snapshot.get("payload") or {}
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    return (
        f"PROVENANCE {symbol} ({capability}) — provider={snapshot.get('provider')} "
        f"eventTime={snapshot.get('eventTime')} quality={snapshot.get('quality')}",
        {"status": "OK", "provenance": {
            "symbol": symbol, "capability": capability,
            "provider": snapshot.get("provider"), "eventTime": snapshot.get("eventTime"),
            "retrievedAt": snapshot.get("retrievedAt"), "quality": snapshot.get("quality"),
            "observationSource": meta.get("observation_source"),
            "lineage": meta.get("source"),
        }},
    )


# ── Registration ─────────────────────────────────────────────────────────────

RESEARCH_DATA_TOOLS: tuple[str, ...] = (
    "resolve_instrument",
    "list_providers",
    "get_provider_health",
    "get_market_data",
    "verify_market_data",
    "resample_data",
    "align_timeseries",
    "build_research_dataset",
    "get_dataset_versions",
    "compare_datasets",
    "query_dataset",
    "get_data_quality_report",
    "get_data_provenance",
    "get_trading_calendar",
    "get_currency_conversion",
    "get_corporate_actions",
    "get_universe",
    "record_universe",
    "list_universes",
    "export_dataset",
    "refresh_dataset",
    "analyze_dataset",
)


def register_research_data_tools(registry: Any) -> list[str]:
    """Register the shared quantitative-research tools on the ONE registry."""
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 45_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=handler, permission="read", risk="low", timeout_ms=timeout,
        ))

    _def(
        "resolve_instrument",
        "Resolve an identifier to a canonical instrument (stable id, asset class, "
        "market, provider symbols, mapping confidence). Never guesses an identity.",
        resolve_instrument,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "market": {"type": "string"}},
            "required": ["symbol"]},
    )
    _def(
        "list_providers",
        "List configured market-data providers and their declared capabilities: "
        "asset classes, intervals, adjustment support, timeliness (realtime/delayed/"
        "eod/reference), credential reference, entitlement and rate limits.",
        list_providers,
        {"type": "object", "properties": {}},
    )
    _def(
        "get_provider_health",
        "Report live provider health: success/failure counts, circuit-breaker state, "
        "observed latency and the durable health mirror. A tripped provider is skipped "
        "by routing rather than silently returning nothing.",
        get_provider_health,
        {"type": "object", "properties": {}},
    )
    _def(
        "get_market_data",
        "Retrieve normalized historical OHLCV for one or more instruments over a date "
        "range with an explicit verification policy. Carries provenance (provider, "
        "timestamps, quality) and, when the policy requires it, an independent "
        "cross-source verification outcome. Never fabricates a bar.",
        get_market_data,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "symbol": {"type": "string"},
            "start": {"type": "string"}, "end": {"type": "string"},
            "interval": {"type": "string", "enum": list(_SERIES_INTERVALS)},
            "adjusted": {"type": "boolean"},
            "provider": {"type": "string", "description": "Pin one provider (explicit selection)."},
            "verification_policy": {"type": "string", "enum": list(policy_names())},
            "tolerance": {"type": "number"},
            "max_bars": {"type": "integer"}}, "required": []},
    )
    _def(
        "verify_market_data",
        "Independently verify a series by retrieving it from two or more providers and "
        "comparing aligned values. Reports verified / unverified / conflicted / failed "
        "under the chosen policy; records material conflicts. Never averages sources.",
        verify_market_data,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "symbol": {"type": "string"},
            "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "adjusted": {"type": "boolean"},
            "policy": {"type": "string", "enum": list(policy_names())},
            "tolerance": {"type": "number"},
            "providers": {"type": "array", "items": {"type": "string"}}},
            "required": []},
    )
    _def(
        "resample_data",
        "Resample OHLCV between intervals with deterministic aggregation (open=first, "
        "high=max, low=min, close=last, volume=sum). Marks partial buckets; refuses to "
        "manufacture intraday bars from a coarser source.",
        resample_data,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "symbol": {"type": "string"},
            "rows": {"type": "array", "items": {"type": "object"},
                     "description": "Inline rows, or omit and pass symbols to fetch."},
            "interval": {"type": "string", "description": "Source interval (fetch mode)."},
            "target_interval": {"type": "string", "enum": list(_SERIES_INTERVALS)},
            "start": {"type": "string"}, "end": {"type": "string"},
            "adjusted": {"type": "boolean"}, "provider": {"type": "string"}},
            "required": ["target_interval"]},
    )
    _def(
        "align_timeseries",
        "Align one or more instruments onto a common timestamp axis (inner/outer join) "
        "with an explicit missing-value policy. Missing values are counted and reported; "
        "forward-fill happens only when explicitly requested.",
        align_timeseries,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "column": {"type": "string"}, "join": {"type": "string", "enum": ["inner", "outer"]},
            "fill": {"description": "omit=null, 'ffill', or a number"},
            "max_points": {"type": "integer"}},
            "required": ["symbols"]},
    )
    _def(
        "build_research_dataset",
        "Build and persist an immutable, versioned research dataset with a manifest "
        "(universe, range, interval, adjustment, per-symbol coverage, quality, lineage, "
        "content hash). Identical content returns the same version; new data creates a "
        "new version and never mutates the old.",
        build_research_dataset,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "start": {"type": "string"}, "end": {"type": "string"},
            "interval": {"type": "string", "enum": list(_SERIES_INTERVALS)},
            "adjusted": {"type": "boolean"},
            "verification_policy": {"type": "string", "enum": list(policy_names())},
            "name": {"type": "string"}, "dataset_id": {"type": "string"},
            "force": {"type": "boolean"}, "tolerance": {"type": "number"}},
            "required": ["symbols"]},
        120_000,
    )
    _def(
        "get_dataset_versions",
        "List the immutable versions of a research dataset and return the latest manifest.",
        get_dataset_versions,
        {"type": "object", "properties": {"dataset_id": {"type": "string"}},
         "required": ["dataset_id"]},
    )
    _def(
        "compare_datasets",
        "Compare two immutable versions of a dataset: symbols added/removed, row-count "
        "and coverage deltas, quality and request changes.",
        compare_datasets,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "version_a": {"type": "string"},
            "version_b": {"type": "string"}},
            "required": ["dataset_id", "version_a", "version_b"]},
    )
    _def(
        "query_dataset",
        "Filter and project a persisted dataset version (symbols, date range, row cap). "
        "Safe, bounded projection only — no arbitrary query language.",
        query_dataset,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "version": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "start": {"type": "string"}, "end": {"type": "string"},
            "as_of": {"type": "string", "description": "Point-in-time cut (kept only when known-at is available)."},
            "limit": {"type": "integer"}},
            "required": ["dataset_id"]},
    )
    _def(
        "get_data_quality_report",
        "Return a data-quality report: for a dataset version, its stored quality and "
        "coverage; otherwise recent market quality findings (optionally for one symbol).",
        get_data_quality_report,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "version": {"type": "string"},
            "symbol": {"type": "string"}, "limit": {"type": "integer"}}},
    )
    _def(
        "get_data_provenance",
        "Return stored provenance for an instrument/capability: provider, event and "
        "retrieval timestamps, observation source, quality and source lineage.",
        get_data_provenance,
        {"type": "object", "properties": {
            "symbol": {"type": "string"}, "capability": {"type": "string"}},
            "required": ["symbol"]},
    )
    _def(
        "get_trading_calendar",
        "Return the trading calendar for a market (us_equity | crypto | fx): whether it "
        "is open now, the next open, holidays (US equities) and session hours. A closed "
        "market is not staleness — the last session close is the freshest legitimate value.",
        get_trading_calendar,
        {"type": "object", "properties": {
            "market": {"type": "string", "enum": ["us_equity", "crypto", "fx"]},
            "asset_type": {"type": "string"}, "year": {"type": "integer"}}},
    )
    _def(
        "get_currency_conversion",
        "Convert an amount between currencies using a direct FX rate, falling back to a "
        "documented cross via USD. A derived rate is labelled `derived=true`; never an "
        "unexplained number.",
        get_currency_conversion,
        {"type": "object", "properties": {
            "base": {"type": "string"}, "quote": {"type": "string"},
            "amount": {"type": "number"}},
            "required": ["base", "quote"]},
    )
    _def(
        "get_corporate_actions",
        "Return corporate actions (splits/dividends) for the requested range as supplied "
        "by the provider. Honest UNAVAILABLE when the provider exposes none — never invented.",
        get_corporate_actions,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "symbol": {"type": "string"},
            "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "adjusted": {"type": "boolean"}},
            "required": []},
    )
    _def(
        "get_universe",
        "Resolve a research universe from symbols/watchlist into canonical instruments. "
        "Membership is resolved from CURRENT identities; historical/as-of membership is "
        "marked UNKNOWN (survivorship-bias guard), never fabricated.",
        get_universe,
        {"type": "object", "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "watchlist": {"type": "array", "items": {"type": "string"}},
            "universe_id": {"type": "string"}, "as_of": {"type": "string"}},
            "required": []},
    )
    _def(
        "export_dataset",
        "Export a persisted dataset version to CSV (per symbol) or JSON under the quant "
        "exports dir, with optional symbol/date/PIT filtering. Reports whether a requested "
        "as-of could actually be enforced.",
        export_dataset,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "version": {"type": "string"},
            "format": {"type": "string", "enum": ["csv", "json"]},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "start": {"type": "string"}, "end": {"type": "string"}, "as_of": {"type": "string"}},
            "required": ["dataset_id"]},
        120_000,
    )
    _def(
        "refresh_dataset",
        "Re-fetch a dataset's inputs and create a NEW immutable version (the previous "
        "version is preserved). Returns the new manifest and a version diff.",
        refresh_dataset,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "from_version": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "adjusted": {"type": "boolean"}},
            "required": ["dataset_id"]},
        120_000,
    )
    _def(
        "record_universe",
        "Record effective-dated universe membership so a research universe can be "
        "resolved as-of a past date. Membership is recorded, never invented — this is "
        "the survivorship-bias control.",
        record_universe,
        {"type": "object", "properties": {
            "universe_id": {"type": "string"}, "name": {"type": "string"},
            "effective_from": {"type": "string"},
            "members": {"type": "array", "items": {"type": "object"},
                        "description": "[{symbol, effectiveFrom, effectiveTo?, meta?}] or [symbol]."},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "as_of": {"type": "string"}},
            "required": ["universe_id"]},
    )
    _def(
        "list_universes",
        "List recorded research universes and their membership counts.",
        list_universes,
        {"type": "object", "properties": {}},
    )
    _def(
        "analyze_dataset",
        "Run deterministic analytics over an immutable dataset version: summary, "
        "returns, volatility, max_drawdown, sharpe, correlation. Declarative only — no "
        "arbitrary code and no provider/secret access.",
        analyze_dataset,
        {"type": "object", "properties": {
            "dataset_id": {"type": "string"}, "version": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "symbol": {"type": "string", "description": "Target symbol (or 'A,B' for correlation)."},
            "operations": {"type": "array", "items": {"type": "string",
                "enum": ["summary", "returns", "volatility", "max_drawdown", "sharpe", "correlation"]}},
            "risk_free_rate": {"type": "number"}, "periods_per_year": {"type": "integer"}},
            "required": ["dataset_id"]},
        60_000,
    )
    return list(RESEARCH_DATA_TOOLS)


__all__ = ["RESEARCH_DATA_TOOLS", "register_research_data_tools"]
