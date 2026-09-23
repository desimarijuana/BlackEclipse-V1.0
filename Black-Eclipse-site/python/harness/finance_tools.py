"""Financial tools — Python-owned contracts, JDdS-backed data.

These are the tools the agents actually call. Their definitions (name, schema,
permission, risk, honesty contract) live here, in the agentic layer. Data comes
from JDdS through the read-only `DataBridge` — the TS side is only the accessor,
so there is still exactly one market-data layer and nothing is fabricated.

Honesty contract (enforced in the tool text, mirrored from the TS vertical
slice): if JDdS has no data, the tool returns an explicit UNAVAILABLE state.
"""

from __future__ import annotations

from typing import Any

from .tools import DataBridge, ToolContext, ToolDefinition, ToolRegistry, dumps


async def _fetch(ctx: ToolContext, capability: str, params: dict[str, Any]) -> dict[str, Any]:
    if ctx.data_bridge is None:
        return {"status": "UNAVAILABLE", "error": "data bridge not configured"}
    return await ctx.data_bridge.fetch(capability, params)


async def get_market_snapshot(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    symbol = str(args.get("symbol", "")).strip().upper()
    market = str(args.get("market", "") or "").strip().upper() or None
    ctx.log("jddS snapshot lookup", {"symbol": symbol, "market": market})

    payload = await _fetch(ctx, "market_snapshot", {"symbol": symbol, "market": market})
    status = payload.get("status", "UNAVAILABLE")
    failure_class = payload.get("failureClass")

    if status != "OK":
        # Derive wording from the failure class (B2), never a single generic line.
        detail = payload.get("error", "")
        if failure_class == "ambiguous" or status == "AMBIGUOUS":
            msg = (
                f"AMBIGUOUS — {detail}\n"
                "Ask the user to specify the market/venue (and share class); do NOT guess."
            )
        elif failure_class == "not_covered":
            msg = f"NOT COVERED — {detail}"
        elif failure_class == "not_found":
            msg = f"UNAVAILABLE — {detail}"
        else:
            msg = (
                f"UNAVAILABLE — no stored snapshot for {symbol}"
                + (f" in market {market}" if market else "")
                + f".\n{detail}"
            )
        return msg, {
            "status": "UNAVAILABLE" if status != "AMBIGUOUS" else "AMBIGUOUS",
            "failureClass": failure_class,
            "symbol": symbol,
            "market": market,
            "source": "JDDS",
        }

    lines = [
        f"Snapshot for {payload.get('symbol', symbol)} — {payload.get('name', '')}",
        f"  Market: {payload.get('exchange', '')} ({payload.get('country', market)})",
        f"  Currency: {payload.get('currency', 'unknown')}",
        f"  Sector: {payload.get('sector') or 'N/A'}",
        f"  Industry: {payload.get('industry') or 'N/A'}",
        f"  Security type: {payload.get('securityType') or 'N/A'}",
    ]
    price = payload.get("price")
    if price:
        lines += [
            f"  Price: {price.get('price')} {payload.get('currency', '')} (per-share)",
            f"  Change: {price.get('changePct')}%",
            f"  Market cap: {price.get('marketCap') if price.get('marketCap') is not None else 'N/A'}",
            f"  Volume: {price.get('volume') if price.get('volume') is not None else 'N/A'}",
            f"  P/E: {price.get('peRatio') if price.get('peRatio') is not None else 'N/A'}",
        ]
    else:
        lines.append("  Price: UNAVAILABLE — the asset exists but has no stored price yet.")
    lines.append(f"Data source: JDDS ({payload.get('priceSource', 'n/a')})")
    lines.append(f"Last updated: {payload.get('updatedAt') or 'unknown'}")
    return "\n".join(lines), {
        "status": "OK",
        "symbol": payload.get("symbol", symbol),
        "market": payload.get("country", market),
        "currency": payload.get("currency"),
        "instrumentId": payload.get("instrumentId"),
        "source": "JDDS",
    }


async def get_fundamentals(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    symbol = str(args.get("symbol", "")).strip().upper()
    payload = await _fetch(ctx, "fundamentals", {"symbol": symbol})
    if payload.get("status") != "OK":
        return f"UNAVAILABLE — no fundamentals stored for {symbol} in JDdS.", {"status": "UNAVAILABLE"}
    return dumps(payload), {"status": "OK", "symbol": symbol}


async def get_news(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query", "") or "")
    payload = await _fetch(ctx, "news", {"query": query})
    failure_class = payload.get("failureClass")
    items = payload.get("items") or []
    source_kind = payload.get("sourceKind", "vault")

    # A source failure must NEVER be phrased as absence of news (B2/C2). An
    # empty result is "no matching data", not "nothing happened".
    if failure_class == "source_failure":
        return (
            "\n".join(
                [
                    "SOURCE FAILURE — the news sources could not be reached.",
                    f"Query: {query!r}",
                    "This is an infrastructure failure, NOT evidence that no news exists. "
                    "Do not report it as 'no news'.",
                    f"Detail: {payload.get('error', '')}",
                ]
            ),
            {"status": "UNAVAILABLE", "failureClass": "source_failure", "count": 0, "source": "JDDS"},
        )
    if not items:
        return (
            f"No matching news stored for {query!r} (sources reachable, no match).",
            {"status": "OK", "failureClass": "no_data", "count": 0, "source": "JDDS"},
        )

    header = (
        f"{len(items)} news item(s) matching {query!r} (source: {source_kind}):"
    )
    lines = [header]
    for i in items:
        lines.append(
            f"[{i.get('source')}] ({i.get('sentiment')}) {i.get('headline')}\n  {i.get('url', '')}"
        )
    return "\n\n".join(lines), {
        "status": "OK",
        "count": len(items),
        "source": source_kind,
        "sourceKind": source_kind,
    }


async def get_source_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    payload = await _fetch(ctx, "source_health", {})
    rows = payload.get("rows") or []
    if not rows:
        # An empty health table is NO DATA, not "everything is fine". Say so.
        return (
            "No source health recorded yet (no_data). Confidence cannot be derived "
            "from history; treat any answer as unverified.",
            {"status": "OK", "failureClass": "no_data", "count": 0},
        )
    lines = ["Source health (per route = provider × market × asset class):"]
    for r in rows:
        rate = r.get("successRate")
        rate_txt = f"{int(rate * 100)}%" if isinstance(rate, (int, float)) else "n/a"
        last = r.get("updatedAt") or "never"
        err = f" lastError={r.get('lastError')}" if r.get("lastError") else ""
        lines.append(
            f"  {r.get('source')} · {r.get('market')} · {r.get('assetClass')}: "
            f"{r.get('health', 'unknown')} — {r.get('success', 0)} ok / {r.get('fail', 0)} fail "
            f"(success {rate_txt}, last {last}){err}"
        )
    lines.append("")
    lines.append(
        "'unknown' means NO ATTEMPTS RECORDED yet — it is neither healthy nor "
        "failing. Only a route with recorded runs can be working or failing."
    )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


async def get_research_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Health of every research retrieval route, WITHOUT running a research task."""
    payload = await _fetch(ctx, "research_health", {})
    rows = payload.get("rows") or []
    if not rows:
        return (
            "No research health could be probed (no_data).",
            {"status": "UNAVAILABLE", "failureClass": "no_data"},
        )
    lines = ["Research retrieval health (per capability):"]
    for r in rows:
        state = "ok" if r.get("ok") else "FAILED"
        detail = f" — {r.get('detail')}" if r.get("detail") else ""
        http = f", HTTP {r.get('httpStatus')}" if r.get("httpStatus") else ""
        lines.append(
            f"  {r.get('provider')} [{r.get('capability')}]: {state} "
            f"({r.get('category')}{http}, {r.get('latencyMs', 0)}ms){detail}"
        )
    lines.append("")
    lines.append(
        "This identifies WHICH capability is failing without a research run. A "
        "failed route is an infrastructure state, not evidence that data is absent."
    )
    return "\n".join(lines), {"status": "OK", "healthy": payload.get("healthy"), "count": len(rows)}


def _fmt_axis(axis: dict[str, Any]) -> str:
    level = str(axis.get("level") or "unknown").replace("_", " ")
    observed = axis.get("observed") or "unknown"
    via = f" via {axis['via']}" if axis.get("via") else ""
    return f"{level}{via} (observed: {observed})"


async def get_capability_matrix(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Truthful per-market capability: what is implemented, configured and observed."""
    payload = await _fetch(ctx, "capability_matrix", {})
    rows = payload.get("rows") or []
    if not rows:
        return (
            "Capability matrix unavailable (no_data).",
            {"status": "UNAVAILABLE", "failureClass": "no_data"},
        )
    lines = ["Capability by market (quote ≠ statements; a listed country is not a promise):"]
    for r in rows:
        universe = r.get("universe")
        universe_txt = "unknown" if universe is None else str(universe)
        lines.append(
            f"  {r.get('market')} ({r.get('currency')}) — instruments in universe: {universe_txt}\n"
            f"      quote: {_fmt_axis(r.get('quote') or {})}\n"
            f"      history: {_fmt_axis(r.get('history') or {})}\n"
            f"      fundamentals: {_fmt_axis(r.get('fundamentals') or {})}\n"
            f"      filings: {_fmt_axis(r.get('filings') or {})}\n"
            f"      web/documents: {_fmt_axis(r.get('web') or {})}"
            + ("  [live-checked]" if r.get("liveChecked") else "")
        )
    lines.append("")
    lines.append(
        "IMPORTANT: a market being listed means it is RECOGNISED, not that every "
        "capability works there. 'fundamentals: not implemented/unconfigured' means "
        "no statement route is available for that market — do NOT infer statements "
        "from a working quote. If a capability is unconfigured, the fix is an "
        "operator-supplied credential, not a different ticker. When a capability is "
        "missing, still try the OTHER eligible routes (web/filing research) before "
        "concluding that evidence is unavailable — unless the USER explicitly "
        "restricted which sources may be used."
    )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


async def get_coverage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Declared market recognition + a compact per-market capability verdict.

    This reports what the app RECOGNISES (a market id/currency/exchange is known)
    separately from what each capability can actually DO there. It deliberately
    does NOT tell the agent to stop when a market or instrument is missing — a
    missing universe row is a reason to try the other eligible routes.
    """
    payload = await _fetch(ctx, "capability_matrix", {})
    rows = payload.get("rows") or []
    if not rows:
        return "Capability matrix is empty.", {"status": "OK", "count": 0}
    lines = ["Recognised markets (market — currency — instruments in universe — key capabilities):"]
    for r in rows:
        universe = r.get("universe")
        universe_txt = "unknown" if universe is None else str(universe)
        quote = str((r.get("quote") or {}).get("level") or "unknown").replace("_", " ")
        fund = str((r.get("fundamentals") or {}).get("level") or "unknown").replace("_", " ")
        filings = str((r.get("filings") or {}).get("level") or "unknown").replace("_", " ")
        lines.append(
            f"  {r.get('market')} — {r.get('currency')} — {universe_txt} — "
            f"quote:{quote}, fundamentals:{fund}, filings:{filings}"
        )
    lines.append("")
    lines.append(
        "A listed market is RECOGNISED; it is NOT a promise that every capability "
        "works there. When a ticker or market is missing from the stored universe, "
        "or a capability is unconfigured, that is NOT a reason to stop: try the other "
        "eligible routes (live quote/history providers, official filings, then "
        "bounded web research) and report what those routes returned before "
        "concluding that evidence is unavailable. Return UNAVAILABLE only when every "
        "eligible route has been tried and none produced the fact. For the full "
        "per-capability detail, use get_capability_matrix."
    )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


def register_finance_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="get_market_snapshot",
            description=(
                "Read a symbol's stored snapshot from JDdS (price, change, market cap, volume, "
                "sector, industry) with explicit provenance and freshness. Returns UNAVAILABLE "
                "when the symbol is not in the vault — it never invents data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL, SYS, BTC."},
                    "market": {"type": "string", "description": "Market/venue code (US, PK, PSX, IN, CRYPTO). Required when the ticker is listed on more than one market; there is no default."},
                },
                "required": ["symbol"],
            },
            handler=get_market_snapshot,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_fundamentals",
            description="Read sector/industry/financial profile for a symbol from JDdS.",
            input_schema={
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "Ticker symbol."}},
                "required": ["symbol"],
            },
            handler=get_fundamentals,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_news",
            description="Read recent stored news headlines/sentiment from JDdS, optionally filtered by keyword.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Optional keyword/ticker filter."}},
            },
            handler=get_news,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_source_health",
            description="Read the reliability/health of each JDdS data source per market, derived from recorded runs.",
            input_schema={"type": "object", "properties": {}},
            handler=get_source_health,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_research_health",
            description=(
                "Probe the health of every research retrieval route (web search, page fetch, "
                "SEC direct) and report which capability is failing, with the structured reason "
                "(timeout/block/http/parse). Use this to diagnose a missing source without "
                "running a full research task. A failed route is not evidence that data is absent."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_research_health,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_capability_matrix",
            description=(
                "Truthful per-market capability: for each recognised market, what is "
                "implemented, configured and observed for quote, history, fundamentals, "
                "official filings and web/document retrieval, plus the instrument-universe "
                "size. Use this to learn whether a market can actually serve a data type — a "
                "listed country is NOT a promise. 'not implemented/unconfigured' means no "
                "route exists for that market yet; try other eligible routes rather than "
                "concluding the data is absent."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_capability_matrix,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_coverage",
            description=(
                "List the markets this system RECOGNISES and a compact capability verdict "
                "(quote/fundamentals/filings) for each. Recognition is not a capability "
                "promise. A ticker or market missing from the stored universe is NOT a reason "
                "to stop: try the other eligible routes before concluding evidence is "
                "unavailable. For full per-capability detail use get_capability_matrix."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_coverage,
            permission="read",
            risk="low",
        )
    )


__all__ = ["register_finance_tools", "DataBridge"]
