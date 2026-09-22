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
        if failure_class == "market_unknown" or status == "AMBIGUOUS":
            msg = (
                f"AMBIGUOUS — {detail}\n"
                "Ask the user to specify the market/venue (and share class); do NOT guess."
            )
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
    lines = ["Source health (derived from recorded runs):"]
    for r in rows:
        rate = r.get("successRate")
        rate_txt = f"{int(rate * 100)}%" if isinstance(rate, (int, float)) else "n/a"
        lines.append(
            f"  {r.get('source')} ({r.get('market')}): {r.get('health', 'unknown')} — "
            f"{r.get('success', 0)} ok / {r.get('fail', 0)} fail (success {rate_txt})"
        )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


async def get_coverage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Declared coverage: which markets/currencies/asset classes are supported."""
    payload = await _fetch(ctx, "coverage", {})
    rows = payload.get("rows") or []
    if not rows:
        return "Coverage registry is empty.", {"status": "OK", "count": 0}
    lines = ["Declared coverage (market — currency — asset classes):"]
    for r in rows:
        classes = ", ".join(r.get("assetClasses", []))
        lines.append(f"  {r.get('market')} — {r.get('currency')} — {classes}")
    lines.append(
        "\nIf a request targets a market/asset class not listed here, it is NOT "
        "COVERED — return UNAVAILABLE rather than trying another source."
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
                    "market": {"type": "string", "description": "Market code (US, PK, IN, CRYPTO). Default US."},
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
            name="get_coverage",
            description=(
                "Declare which markets, currencies and asset classes this system has a "
                "data source for. Use before assuming a market is supported."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_coverage,
            permission="read",
            risk="low",
        )
    )


__all__ = ["register_finance_tools", "DataBridge"]
