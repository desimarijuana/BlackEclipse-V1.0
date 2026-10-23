"""Initial financial retrieval tools (Milestone 2L).

These tools call the **Financial Retrieval Layer**, never a provider directly.
The shape is always:

    tool → retrieval layer → planner → sources → normalize → validate →
    provenance → tool result

The tool contracts (name, schema, permission, risk) still live in the agentic
layer. The tools are read-only. Every tool returns a plain-text summary for the
model plus a structured `data` object for the runtime/evidence.

Tool names follow the `domain.verb` convention from the Phase-2 brief:
    market.get_quote, market.get_ohlcv,
    fundamentals.get_company_profile, fundamentals.get_financials,
    research.search, research.retrieve_source, research.search_news,
    macro.get_series
"""

from __future__ import annotations

from typing import Any, Optional

from .retrieval import (
    DataType,
    FinancialRetrievalLayer,
    FinancialRetrievalRequest,
)
from .macro_identity import resolve_macro_series
from .tools import ToolContext, ToolDefinition, ToolRegistry, dumps

# The registry's tool-name validator allows only [A-Za-z0-9_]. These are the
# canonical Phase-2 names, dotted as specified, mapped at registration time.
_TOOL_NAMES = {
    "market.get_quote": "market_get_quote",
    "market.get_ohlcv": "market_get_ohlcv",
    "fundamentals.get_company_profile": "fundamentals_get_company_profile",
    "fundamentals.get_financials": "fundamentals_get_financials",
    "research.search": "research_search",
    "research.retrieve_source": "research_retrieve_source",
    "research.search_news": "research_search_news",
    "macro.get_series": "macro_get_series",
    # Financial Data Gateway surface (provider introspection + crypto).
    "financial.providers": "financial_providers",
    "financial.resolve_entity": "financial_resolve_entity",
    "market.get_crypto": "market_get_crypto",
}


def _layer(ctx: ToolContext) -> FinancialRetrievalLayer:
    """Get (or lazily build) the run's retrieval layer from the context.

    The layer (and its cache) is per-run, so repeated tool calls in one run
    reuse a retrieval instead of re-hitting a provider. The cache is shared on
    the context so a run can also expose it to the harness metrics.
    """
    layer = getattr(ctx, "retrieval", None)
    if layer is None:
        cache = getattr(ctx, "retrieval_cache", None)
        store = getattr(ctx, "memory_store", None)
        mcp_manager = getattr(ctx, "mcp_manager", None)
        mcp_sources = []
        if mcp_manager is not None:
            try:
                mcp_sources = mcp_manager.mcp_sources()
            except Exception:  # noqa: BLE001 - MCP sources are optional
                mcp_sources = []
        layer = FinancialRetrievalLayer(
            ctx.data_bridge, cache=cache, on_event=_event_logger(ctx), store=store,
            mcp_sources=mcp_sources, registry=_provider_registry(ctx),
        )
        ctx.retrieval = layer  # type: ignore[attr-defined]
        ctx.retrieval_cache = layer.cache  # type: ignore[attr-defined]
    return layer


def _provider_registry(ctx: ToolContext):
    """The process-wide provider registry, or a fresh default one.

    The service installs ONE registry at boot so the agent tools and the layer
    describe the same providers. A unit test with no service gets a default
    registry (still deterministic, still one row per provider).
    """
    registry = getattr(ctx, "provider_registry", None)
    if registry is not None:
        return registry
    from .retrieval.registry import build_default_registry

    return build_default_registry()


def _event_logger(ctx: ToolContext):
    """Forward retrieval-layer events to the run's emitter.

    The retrieval layer emits `retrieval.*` events (planned, cache_hit,
    source_start, source_ok, source_unavailable). These must ride the run's SSE
    stream so the UI can show which sources were consulted and whether any
    failed — a plain `ctx.log` no-op would discard them. Falls back to the log
    callback when no emitter is attached (e.g. unit tests).
    """
    emitter = getattr(ctx, "emitter", None)

    async def _log(event_type: str, data: dict[str, Any]) -> None:
        if emitter is not None:
            await emitter.emit(event_type, data)
        else:
            ctx.log(f"retrieval:{event_type}", data)

    return _log


def _collect(ctx: ToolContext, result: Any, analysis: Any = None) -> None:
    """Hand a retrieval result to the run's source collector, when one is attached.

    Ordinary chat runs collect provenance so the answer can show a Sources panel
    (built only from what was actually retrieved). A run with no sink (tests, or
    the gated research path) simply skips this — collection is additive and must
    never affect the tool's returned text. The finance `analysis` is passed through
    so the run can enforce disclosures on the final answer without recomputing it.
    """
    sink = getattr(ctx, "source_sink", None)
    if sink is None:
        return
    try:
        sink.add(result, analysis) if analysis is not None else sink.add(result)
    except Exception:  # noqa: BLE001 - provenance collection must never break a tool
        pass


def _finish(ctx: ToolContext, result: Any) -> tuple[str, Any]:
    """Collect provenance (when enabled) and return the standard tool tuple.

    The structured payload gains an `analysis` block: the validated fact set,
    gate verdicts, conflicts and notes. Additive and best-effort — a failure in
    analysis must never break the tool, so it degrades to the original payload.
    The analysis is computed ONCE and shared with the text summary.
    """
    payload = result.model_dump()
    try:
        from .market.quality_contract import DataQualityEnvelope

        verdict = {
            "OK": "VALID", "STALE": "STALE", "CONFLICTING": "DIVERGENT",
            "UNAVAILABLE": "UNAVAILABLE", "AMBIGUOUS": "UNVERIFIED",
            "INVALID": "UNAVAILABLE", "PARTIAL": "UNVERIFIED",
        }.get(str(result.status), "UNVERIFIED")
        if result.quality == "warning" and verdict == "VALID":
            verdict = "UNVERIFIED"
        providers = [r.source for r in result.sourceReferences if r.source]
        obs = None
        for item in result.evidence:
            for obj in getattr(item, "objects", []) or []:
                if getattr(obj, "observation_time", None) or getattr(obj, "dataTimestamp", None):
                    obs = obj.observation_time or obj.dataTimestamp
                    break
            if obs:
                break
        payload["envelope"] = DataQualityEnvelope(
            provider=",".join(dict.fromkeys(providers)) or None,
            observationTimestamp=obs,
            retrievalTimestamp=result.retrievedAt,
            qualityVerdict=verdict,
            conflicts=[
                {
                    "metric": c.get("metric") or "value",
                    "candidates": c.get("candidates") or [],
                }
                for c in result.conflicts
            ],
            stale=bool(getattr(result, "stale", False)),
            reasonCode=getattr(result, "reasonCode", None),
        ).to_dict()
    except Exception:  # noqa: BLE001 - the envelope is additive, never fatal
        pass
    analysis = None
    try:
        from .finance_facts.analysis import analyze_result

        analysis = analyze_result(result)
        payload["analysis"] = analysis.to_dict()
    except Exception:  # noqa: BLE001 - analysis is additive, never fatal
        analysis = None
    # The analysis also rides the run's provenance collector so the FINAL answer
    # can be checked against what was actually retrieved (finance_facts.enforce).
    _collect(ctx, result, analysis)
    return _summarize(result, analysis=analysis), payload


def _record_fetched(
    ctx: ToolContext,
    *,
    url: str,
    title: Any = None,
    ok: bool = True,
    published_at: Any = None,
    retrieved_at: Any = None,
) -> None:
    """Record a directly-fetched URL on the run's collector, when one is attached."""
    sink = getattr(ctx, "source_sink", None)
    if sink is None:
        return
    try:
        sink.add_fetched_source(
            url=url,
            title=(str(title) if title else None),
            ok=ok,
            published_at=(str(published_at) if published_at else None),
            retrieved_at=(str(retrieved_at) if retrieved_at else None),
        )
    except Exception:  # noqa: BLE001 - provenance collection must never break a tool
        pass


def _summarize(result: Any, analysis: Any = None) -> str:
    """A compact, honest text summary of a retrieval result."""
    lines = [
        f"Retrieval status: {result.status}",
        f"Data type: {result.dataType}",
        f"Strategy: {', '.join(result.strategy) or 'none'}",
        f"Freshness: {result.freshness} | Quality: {result.quality}",
    ]
    if result.identity is not None:
        lines.append(
            f"Instrument: {result.identity.symbol} on {result.identity.market}"
            + (f" ({result.identity.currency})" if result.identity.currency else "")
        )
    if result.cached:
        lines.append("Served from cache.")
    if result.data is not None:
        lines.append("")
        lines.append(_render_data(result.data))
    if result.evidence:
        lines.append("")
        # The count and the list must agree. The summary is bounded for context
        # size, so when the list is truncated we SAY so and give the true total —
        # otherwise a reader sees "evidenceCount=N" beside a shorter list and
        # reasonably concludes items were dropped silently (Issue 5).
        total = len(result.evidence)
        shown = result.evidence[:6]
        lines.append(f"Evidence ({len(shown)} of {total} shown):")
        for item in shown:
            lines.append(f"  [{item.kind}/{item.quality}] {item.summary[:240]}")
            if item.source.url:
                lines.append(f"    {item.source.url}")
        if total > len(shown):
            lines.append(f"  …and {total - len(shown)} more evidence item(s) not shown.")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in result.warnings[:8])
    if result.status == "AMBIGUOUS":
        lines.append("")
        lines.append(
            "AMBIGUOUS — the ticker does not identify a single instrument. Ask the "
            "user which market/venue (and share class) they mean; do NOT guess."
        )
    if result.status == "UNAVAILABLE":
        lines.append("")
        lines.append(
            "No data was fabricated. Before concluding, try the other eligible routes the "
            "bound tools offer — another provider, the official filing, bounded web search, "
            "web_scrape for one page's structured data, or the browser for a rendered page. "
            "Only once those routes are exhausted is an explicit UNAVAILABLE the correct answer."
        )
    # Universal-financial-fact analysis (additive, §1/§3/§4/§12/§26): name the
    # accounting-definition ambiguity, the business type, any cross-source
    # disagreement and any stale value — so the model reasons OVER validated facts
    # rather than assuming. Absent when there is nothing to disclose.
    try:
        if analysis is None:
            from .finance_facts.analysis import analyze_result

            analysis = analyze_result(result)
        if analysis.notes:
            lines.append("")
            lines.append("Data-quality notes:")
            lines.extend(f"  - {n}" for n in analysis.notes[:8])
        if analysis.excluded:
            lines.append(f"  - withheld from a clean answer: {', '.join(analysis.excluded)}")
    except Exception:  # noqa: BLE001 - analysis must never break the summary
        pass
    lines.append(f"Retrieved at: {result.retrievedAt}")
    return "\n".join(lines)


def _render_data(data: Any) -> str:
    if isinstance(data, dict):
        return "\n".join(f"  {k}: {v}" for k, v in list(data.items())[:40])
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return "\n".join("  " + ", ".join(f"{k}={v}" for k, v in row.items()) for row in data[:30])
        return dumps(data[:30])
    return str(data)


# ── Handlers ────────────────────────────────────────────────────────────────


async def market_get_quote(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    # D3: FX has ONE canonical resolver. Every FX entry point (get_fx_rate,
    # get_currency_conversion, market_get_quote) routes through the same gateway
    # method, so all three return the same instrument, rate and timestamp (or
    # the same named refusal).
    from .market.errors import MarketError
    from .market.gateway import MarketDataGateway
    from .market.instruments import classify_identifier

    symbol = str(args.get("symbol", "")).strip().upper()
    market = (str(args["market"]).strip().upper() if args.get("market") else None)
    kind = classify_identifier(symbol, market)
    if kind.get("kind") == "fx":
        gateway = getattr(ctx, "market_gateway", None) or MarketDataGateway(
            getattr(ctx, "data_bridge", None)
        )
        try:
            ctx.market_gateway = gateway  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        fx = await gateway.get_fx_rate(
            base=kind.get("base"), quote=kind.get("quote"), symbol=symbol,
            freshness="realtime",
        )
        if isinstance(fx, MarketError):
            return (f"UNAVAILABLE — {fx.code}: {fx.message}",
                    {"status": "UNAVAILABLE", "error": fx.to_dict(),
                     "reasonCode": fx.code, "qualityVerdict": "UNAVAILABLE"})
        rate = fx.mid or fx.rate
        return (
            f"FX {fx.base}/{fx.quote}: {rate} (provider {fx.meta.provider})",
            {"status": "OK", "rate": rate, "base": fx.base, "quote": fx.quote,
             "timestamp": fx.meta.event_time, "asOf": fx.meta.event_time,
             "provider": fx.meta.provider, "qualityVerdict": "VALID",
             "instrumentId": fx.meta.instrument_id,
             "envelope": {"value": rate, "unit": "rate", "currency": fx.quote,
                          "provider": fx.meta.provider,
                          "observationTimestamp": fx.meta.event_time,
                          "retrievalTimestamp": fx.meta.retrieved_at,
                          "nativeCadence": "realtime", "qualityVerdict": "VALID",
                          "conflicts": [], "routesSkipped": [], "stale": False,
                          "reasonCode": None}},
        )

    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"latest quote for {args.get('symbol', '')}"),
        dataType="current_quote",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        freshnessRequirement="realtime",
        allowWeb=bool(args.get("allow_web", False)),
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def market_get_ohlcv(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    date_range: Optional[dict[str, str]] = None
    if args.get("start") or args.get("end"):
        date_range = {}
        if args.get("start"):
            date_range["start"] = str(args["start"])
        if args.get("end"):
            date_range["end"] = str(args["end"])
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"historical prices for {args.get('symbol', '')}"),
        dataType="historical_prices",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        dateRange=date_range,
        freshnessRequirement="slow",
        # An explicit window supersedes the range default: otherwise the default
        # `period` overwrote the requested start and the full history came back.
        quantity=None if date_range else str(args.get("period", "1y") or "1y"),
        allowWeb=False,  # a series is never sourced from search results
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def fundamentals_get_company_profile(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"company profile for {args.get('symbol', '')}"),
        dataType="company_profile",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        freshnessRequirement="slow",
        allowWeb=bool(args.get("allow_web", True)),
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def fundamentals_get_financials(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"financial statements for {args.get('symbol', '')}"),
        dataType="financial_statements",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        freshnessRequirement="slow",
        allowWeb=bool(args.get("allow_web", False)),
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def research_search(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query", "") or "")
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or query or "web research"),
        dataType="web_research",
        instrument=(str(args["symbol"]).strip().upper() if args.get("symbol") else None),
        query=query,
        freshnessRequirement="daily",
        allowWeb=True,
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def research_search_news(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query", "") or "")
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or query or "current news"),
        dataType="news",
        instrument=(str(args["symbol"]).strip().upper() if args.get("symbol") else None),
        query=query,
        freshnessRequirement="intraday",
        allowWeb=True,
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def research_retrieve_source(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    url = str(args.get("url", "") or "").strip()
    if not url:
        return "UNAVAILABLE — a url is required to retrieve a source.", {"status": "UNAVAILABLE"}
    if ctx.data_bridge is None:
        return "UNAVAILABLE — data bridge not configured.", {"status": "UNAVAILABLE"}
    payload = await ctx.data_bridge.fetch("web_fetch", {"url": url})
    if payload.get("status") != "OK":
        # Surface WHY it failed (category), so the agent can escalate to another
        # route rather than reading every miss as "the document does not exist".
        diagnostics = payload.get("diagnostics") or []
        category = diagnostics[0].get("category") if diagnostics else None
        hint = ""
        if category == "unsupported_document":
            hint = " The document was FETCHED but has no extractable text (likely a scanned/image PDF); OCR is unavailable — try another source."
        elif category == "javascript_only":
            hint = " The page is a JavaScript-only shell with no server-rendered text — try an alternate official source."
        elif category == "too_large":
            hint = " The document exceeded the size cap. It was not read; try a specific section, a smaller document, or another source."
        elif category == "empty_response":
            hint = " The remote returned an empty body — treat as no evidence, not as a document with no values."
        elif category == "parse_failure":
            hint = " The document was fetched but no values could be extracted (e.g. a value-less taxonomy) — it is not evidence."
        elif category == "blocked":
            hint = " The host refused or blocked the request (anti-bot/robots). This is not evidence that the document does not exist."
        elif category == "no_instrument":
            hint = " The document could not be attributed to the requested instrument."
        elif category in ("timeout", "transport_error", "http_error"):
            hint = " This is a retrieval/transport failure, not evidence that the document does not exist."
        _record_fetched(ctx, url=url, title=None, ok=False)
        return (
            f"UNAVAILABLE — the source at {url} could not be retrieved "
            f"({payload.get('error', 'unknown reason')}; category={category}). It is not treated as verified.{hint}",
            {"status": "UNAVAILABLE", "url": url, "category": category},
        )
    text = str(payload.get("text") or "")[:6000]
    # D11: "fetched but zero text" is IMAGE_ONLY, never an empty success. If OCR
    # is not available, say OCR_UNAVAILABLE and name the missing capability.
    if not text.strip():
        _record_fetched(ctx, url=url, title=None, ok=False)
        from .vision.ocr import ocr_available

        if ocr_available():
            return (
                f"IMAGE_ONLY — {url} was fetched but has no extractable text "
                "(scanned/image-only document). It was NOT read; it has been routed "
                "to the OCR path.",
                {"status": "IMAGE_ONLY", "url": url, "text": "",
                 "documentStatus": "IMAGE_ONLY", "ocrAvailable": True,
                 "reasonCode": "IMAGE_ONLY"},
            )
        return (
            f"OCR_UNAVAILABLE — {url} was fetched but has no extractable text "
            "(scanned/image-only document), and this runtime has no OCR capability. "
            "The document was NOT read; do not treat it as evidence.",
            {"status": "OCR_UNAVAILABLE", "url": url, "text": "",
             "documentStatus": "IMAGE_ONLY", "ocrAvailable": False,
             "missingCapability": "OCR", "reasonCode": "OCR_UNAVAILABLE"},
        )
    title = payload.get("title") or url
    extraction = payload.get("extraction")
    language = payload.get("language")
    document_id = payload.get("documentId")
    published_at = payload.get("publishedAt")
    retrieved_at = payload.get("retrievedAt")
    _record_fetched(
        ctx, url=url, title=title, ok=True,
        published_at=published_at, retrieved_at=retrieved_at,
    )
    meta_bits = []
    if extraction:
        meta_bits.append(f"extracted via {extraction}")
    if language:
        meta_bits.append(f"language={language}")
    if document_id:
        meta_bits.append(f"documentId={document_id}")
    if published_at:
        meta_bits.append(f"published={published_at}")
    if retrieved_at:
        meta_bits.append(f"retrieved={retrieved_at}")
    meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
    body = f"Retrieved source: {title}\nURL: {url}{meta}\n\n{text}"
    return body, {
        "status": "OK",
        "url": url,
        "title": title,
        "text": text,
        "extraction": extraction,
        "language": language,
        "documentId": document_id,
        "publishedAt": published_at,
        "retrievedAt": retrieved_at,
    }


async def macro_get_series(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    series = str(args.get("series", "") or "")
    geography = str(args.get("geography") or args.get("country") or "").strip() or None

    # Resolve the series identity before touching a source. The TS registry is
    # the single source of truth (one alias table); the local resolver is only a
    # fallback when the bridge is unavailable, so the two cannot drift silently.
    resolved = await _resolve_macro_via_bridge(ctx, series, geography)
    if resolved is None:
        resolved = resolve_macro_series(series, geography)
    if not resolved["ok"]:
        reason = resolved["reason"]
        candidates = resolved.get("candidates")
        msg = (
            f"{reason.upper()} — {resolved['message']}"
            + (f" Candidates: {', '.join(candidates)}." if candidates else "")
        )
        return msg, {
            "status": "AMBIGUOUS" if reason == "ambiguous" else "UNAVAILABLE",
            "failureClass": reason,
            "candidates": candidates,
        }

    identity = resolved["identity"]
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"macro series {series}"),
        dataType="macro_series",
        instrument=identity["id"],
        quantity=identity.get("providerSeries") or series,
        market=identity.get("geography"),
        freshnessRequirement="slow",
        allowWeb=False,  # precise macro history is never web-sourced
        metadata={"source": args.get("source") or identity.get("sourceId") or None},
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


async def _resolve_macro_via_bridge(
    ctx: ToolContext, series: str, geography: Optional[str]
) -> Optional[dict[str, Any]]:
    """Ask the bridge to resolve the macro identity (the TS registry is canonical).

    Returns a normalised `{"ok": True/False, ...}` dict, or None when the bridge
    cannot answer (then the caller falls back to the local resolver).
    """
    if ctx.data_bridge is None:
        return None
    try:
        payload = await ctx.data_bridge.fetch(
            "macro_resolve", {"series": series, "geography": geography}
        )
    except Exception:  # noqa: BLE001 - fall back to the local resolver
        return None
    if payload.get("status") == "OK" and isinstance(payload.get("identity"), dict):
        return {"ok": True, "identity": payload["identity"]}
    if payload.get("failureClass") in ("ambiguous", "not_covered", "not_found"):
        return {
            "ok": False,
            "reason": payload["failureClass"],
            "message": payload.get("error") or "macro series could not be resolved",
            "candidates": payload.get("candidates"),
        }
    return None


# ── Financial Data Gateway: provider introspection + crypto ─────────────────


async def financial_providers(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Describe the configured financial providers and their capabilities.

    Reads the ONE provider registry: each provider's capabilities, credential
    reference (never a value), implemented/degraded state, rate-limit shape and
    recorded data-usage policy. An option filters to one capability.
    """
    registry = _provider_registry(ctx)
    capability = str(args.get("capability", "") or "").strip() or None
    providers = registry.by_capability(capability) if capability else registry.all()

    # Resolve live configuration for credentialed providers without ever returning
    # the secret — only whether the credential is present (env or vault).
    rows: list[dict[str, Any]] = []
    for descriptor in providers:
        entry = descriptor.to_dict()
        if descriptor.credential_ref and descriptor.configured is None:
            entry["configured"] = await _credential_present(ctx, descriptor.credential_ref)
        rows.append(entry)

    lines = [f"Financial data providers ({len(rows)}"
             + (f" supporting '{capability}'" if capability else "") + "):"]
    for entry in rows:
        state = "implemented" if entry.get("implemented") else "declared (not implemented)"
        if entry.get("configured") is True:
            state += ", credential configured"
        elif entry.get("configured") is False:
            state += ", credential missing"
        lines.append(
            f"  - {entry['id']} ({entry['label']}) [{entry.get('tier')}] — {state}"
        )
        lines.append(f"      capabilities: {', '.join(entry.get('capabilities') or []) or 'none'}")
        if entry.get("notes"):
            lines.append(f"      note: {entry['notes']}")
    lines.append("")
    lines.append(
        "A provider listed as 'declared (not implemented)' has no runnable adapter yet — "
        "its dependency is named, not faked. Credentials are never shown; only their presence."
    )
    return "\n".join(lines), {"providers": rows, "capability": capability}


async def _credential_present(ctx: ToolContext, env_var: str) -> bool:
    """Whether a provider credential is satisfied, checked via the bridge.

    The vault lives on the TS side; the bridge answers presence (never the value).
    Falls back to the process environment when no bridge is attached or the bridge
    cannot answer.
    """
    bridge = getattr(ctx, "data_bridge", None)
    if bridge is not None:
        try:
            payload = await bridge.fetch("provider_key_status", {"envVar": env_var})
        except Exception:  # noqa: BLE001 - a probe failure falls back to env
            payload = None
        if isinstance(payload, dict) and "configured" in payload:
            return bool(payload["configured"])
    import os

    return bool(os.environ.get(env_var))


async def financial_resolve_entity(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Resolve a financial identifier to a canonical instrument identity.

    Accepts a ticker, an exchange-qualified symbol (`NASDAQ:AAPL`), or an ISIN,
    and asks the bridge's shared instrument resolver. Never guesses: an
    unresolved identifier returns UNAVAILABLE, an ambiguous one returns AMBIGUOUS.
    """
    identifier = str(args.get("identifier", "") or "").strip()
    if not identifier:
        return "UNAVAILABLE — an identifier is required.", {"status": "UNAVAILABLE"}
    if ctx.data_bridge is None:
        return "UNAVAILABLE — data bridge not configured.", {"status": "UNAVAILABLE"}
    params: dict[str, Any] = {"symbol": identifier}
    if args.get("market"):
        params["market"] = str(args["market"]).strip().upper()
    try:
        payload = await ctx.data_bridge.fetch("market_snapshot", params)
    except Exception as exc:  # noqa: BLE001
        return f"UNAVAILABLE — identity resolution failed ({exc}).", {"status": "UNAVAILABLE"}
    status = payload.get("status")
    if status == "OK":
        identity = {
            "symbol": payload.get("symbol"),
            "market": payload.get("market"),
            "exchange": payload.get("exchange"),
            "currency": payload.get("currency"),
            "securityType": payload.get("securityType"),
            "assetClass": payload.get("assetClass"),
            "instrumentId": payload.get("instrumentId"),
            "name": payload.get("name"),
        }
        text = (
            f"Resolved {identifier} → {identity['symbol']} on {identity['market']}"
            + (f" ({identity['exchange']})" if identity.get("exchange") else "")
            + (f" [{identity['securityType']}]" if identity.get("securityType") else "")
            + (f", currency {identity['currency']}" if identity.get("currency") else "")
        )
        return text, {"status": "OK", "identity": identity}
    if payload.get("failureClass") == "ambiguous":
        candidates = payload.get("candidates")
        msg = f"AMBIGUOUS — {identifier} matches more than one instrument; ask which venue."
        if candidates:
            msg += f" Candidates: {', '.join(map(str, candidates))}."
        return msg, {"status": "AMBIGUOUS", "candidates": candidates}
    return (
        f"UNAVAILABLE — {identifier} could not be resolved "
        f"({payload.get('error') or 'not found'}).",
        {"status": "UNAVAILABLE", "error": payload.get("error")},
    )


async def market_get_crypto(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Get a crypto asset's market data through the retrieval layer.

    A crypto pair is resolved (base/quote) and routed to the dedicated crypto
    source. Never confuses a crypto ticker with an equity or an FX pair.
    """
    symbol = str(args.get("symbol", "") or "").strip().upper()
    metadata: dict[str, Any] = {}
    if args.get("quote_currency"):
        metadata["quoteCurrency"] = str(args["quote_currency"]).strip().upper()
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"crypto market data for {symbol}"),
        dataType="current_quote",
        instrument=symbol,
        market="CRYPTO",
        freshnessRequirement="realtime",
        allowWeb=False,
        metadata=metadata or None,
    )
    result = await _layer(ctx).retrieve(request)
    return _finish(ctx, result)


# ── Registration ────────────────────────────────────────────────────────────

def register_retrieval_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["market.get_quote"],
            description=(
                "Get the latest price/change for an instrument through the unified retrieval "
                "layer. Selects the best structured source (vault or live provider); never "
                "invents a price. Returns UNAVAILABLE when no precise source has data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL."},
                    "market": {"type": "string", "description": "Market code (US, PK, IN, CRYPTO)."},
                    "objective": {"type": "string", "description": "Why this data is needed (optional)."},
                    "allow_web": {"type": "boolean", "description": "Allow a web fallback (default false)."},
                },
                "required": ["symbol"],
            },
            handler=market_get_quote,
            permission="read",
            risk="low",
            timeout_ms=15_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["market.get_ohlcv"],
            description=(
                "Get a historical OHLCV series through the retrieval layer. This requires a "
                "precise structured dataset; it will never search the web for prices and "
                "returns UNAVAILABLE if none is available."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol."},
                    "market": {"type": "string", "description": "Market code."},
                    "period": {"type": "string", "description": "Range, e.g. 1mo, 6mo, 1y, 5y."},
                    "start": {"type": "string", "description": "Optional start date (YYYY-MM-DD). With a window, this supersedes `period`."},
                    "end": {"type": "string", "description": "Optional end date (YYYY-MM-DD, inclusive)."},
                    "objective": {"type": "string", "description": "Why this data is needed (optional)."},
                },
                "required": ["symbol"],
            },
            handler=market_get_ohlcv,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["fundamentals.get_company_profile"],
            description="Get a company's profile (sector, industry, exchange, description) via the retrieval layer.",
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol."},
                    "market": {"type": "string", "description": "Market code."},
                    "allow_web": {"type": "boolean", "description": "Allow web context (default true)."},
                },
                "required": ["symbol"],
            },
            handler=fundamentals_get_company_profile,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["fundamentals.get_financials"],
            description="Get reported financial statements (periods/metrics) through the retrieval layer.",
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol."},
                    "market": {"type": "string", "description": "Market code."},
                    "allow_web": {"type": "boolean", "description": "Allow primary-source web context."},
                },
                "required": ["symbol"],
            },
            handler=fundamentals_get_financials,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["research.search"],
            description=(
                "Run web research through the retrieval layer: search, retrieve the underlying "
                "page, and return provenance-carrying evidence. Prefers primary sources."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The research query."},
                    "symbol": {"type": "string", "description": "Optional instrument the query is about."},
                    "objective": {"type": "string", "description": "The underlying objective."},
                },
                "required": ["query"],
            },
            handler=research_search,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["research.retrieve_source"],
            description=(
                "Retrieve and read a specific URL (e.g. a filing or IR page) as evidence. "
                "Marks the source unverified rather than pretending it was read when it cannot be fetched."
            ),
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The source URL to retrieve."}},
                "required": ["url"],
            },
            handler=research_retrieve_source,
            permission="read",
            risk="low",
            timeout_ms=20_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["research.search_news"],
            description="Get current financial news / commentary through the retrieval layer.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional keyword or ticker filter."},
                    "symbol": {"type": "string", "description": "Optional instrument."},
                },
            },
            handler=research_search_news,
            permission="read",
            risk="low",
            # News is an OPTIONAL enrichment step. It keeps its OWN bounded
            # timeout so a slow news provider can never consume the whole run or
            # cancel financial-statement retrieval / partial-answer rendering
            # (WS2). It is deliberately shorter than a statement fetch.
            timeout_ms=12_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["macro.get_series"],
            description=(
                "Get a macro-economic series through the retrieval layer. Requires a precise "
                "structured source; returns UNAVAILABLE rather than web-sourcing a number."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "series": {
                        "type": "string",
                        "description": (
                            "Series id (CPIAUCSL, or a canonical id like US:FRED:FEDFUNDS). "
                            "A generic measure such as 'policy rate' requires `geography`."
                        ),
                    },
                    "geography": {
                        "type": "string",
                        "description": (
                            "Country/market the series is about (US, EA, GB, …). Required to "
                            "disambiguate a generic measure; never defaults to the US."
                        ),
                    },
                    "source": {"type": "string", "description": "Optional macro source id, e.g. fred-analytics."},
                    "objective": {"type": "string", "description": "Why this series is needed."},
                },
                "required": ["series"],
            },
            handler=macro_get_series,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["financial.providers"],
            description=(
                "List the configured financial data providers through the gateway: each provider's "
                "capabilities, whether it is implemented, its credential presence (never the secret), "
                "rate-limit shape and recorded data-usage policy. Optionally filter by capability."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "capability": {
                        "type": "string",
                        "description": "Optional capability filter, e.g. current_quote, financial_statements, crypto_market_data.",
                    },
                },
            },
            handler=financial_providers,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["financial.resolve_entity"],
            description=(
                "Resolve a financial identifier (ticker, exchange-qualified symbol, or ISIN) to a "
                "canonical instrument identity. Never guesses: an ambiguous identifier returns "
                "AMBIGUOUS and an unknown one returns UNAVAILABLE."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "Ticker, NASDAQ:AAPL, or an ISIN."},
                    "market": {"type": "string", "description": "Optional market code to disambiguate."},
                },
                "required": ["identifier"],
            },
            handler=financial_resolve_entity,
            permission="read",
            risk="low",
            timeout_ms=15_000,
        )
    )
    registry.register(
        ToolDefinition(
            name=_TOOL_NAMES["market.get_crypto"],
            description=(
                "Get a crypto asset's market data through the retrieval layer. Resolves the "
                "base/quote pair and routes to the dedicated crypto source; never confuses a crypto "
                "ticker with an equity or an FX pair."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Crypto base asset or pair, e.g. BTC or BTC-USD."},
                    "quote_currency": {"type": "string", "description": "Optional quote currency (USD, USDT, EUR)."},
                    "objective": {"type": "string", "description": "Why this data is needed (optional)."},
                },
                "required": ["symbol"],
            },
            handler=market_get_crypto,
            permission="read",
            risk="low",
            timeout_ms=15_000,
        )
    )


__all__ = ["register_retrieval_tools", "_TOOL_NAMES"]
