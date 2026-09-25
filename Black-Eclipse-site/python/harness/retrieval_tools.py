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
        layer = FinancialRetrievalLayer(
            ctx.data_bridge, cache=cache, on_event=_event_logger(ctx), store=store
        )
        ctx.retrieval = layer  # type: ignore[attr-defined]
        ctx.retrieval_cache = layer.cache  # type: ignore[attr-defined]
    return layer


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


def _summarize(result: Any) -> str:
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
            "No data was fabricated. If this is a precise quantitative request, "
            "an explicit UNAVAILABLE is the correct answer rather than a web guess."
        )
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
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"latest quote for {args.get('symbol', '')}"),
        dataType="current_quote",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        freshnessRequirement="realtime",
        allowWeb=bool(args.get("allow_web", False)),
    )
    result = await _layer(ctx).retrieve(request)
    return _summarize(result), result.model_dump()


async def market_get_ohlcv(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    request = FinancialRetrievalRequest(
        objective=str(args.get("objective") or f"historical prices for {args.get('symbol', '')}"),
        dataType="historical_prices",
        instrument=str(args.get("symbol", "")).strip().upper(),
        market=(str(args["market"]).strip().upper() if args.get("market") else None),
        dateRange={"start": str(args.get("start", ""))} if args.get("start") else None,
        freshnessRequirement="slow",
        quantity=str(args.get("period", "1y") or "1y"),
        allowWeb=False,  # a series is never sourced from search results
    )
    result = await _layer(ctx).retrieve(request)
    return _summarize(result), result.model_dump()


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
    return _summarize(result), result.model_dump()


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
    return _summarize(result), result.model_dump()


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
    return _summarize(result), result.model_dump()


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
    return _summarize(result), result.model_dump()


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
        return (
            f"UNAVAILABLE — the source at {url} could not be retrieved "
            f"({payload.get('error', 'unknown reason')}; category={category}). It is not treated as verified.{hint}",
            {"status": "UNAVAILABLE", "url": url, "category": category},
        )
    text = str(payload.get("text") or "")[:6000]
    title = payload.get("title") or url
    extraction = payload.get("extraction")
    language = payload.get("language")
    document_id = payload.get("documentId")
    published_at = payload.get("publishedAt")
    retrieved_at = payload.get("retrievedAt")
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
    return _summarize(result), result.model_dump()


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
                    "start": {"type": "string", "description": "Optional start date (YYYY-MM-DD)."},
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


__all__ = ["register_retrieval_tools", "_TOOL_NAMES"]
