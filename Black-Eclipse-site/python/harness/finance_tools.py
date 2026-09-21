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
    market = str(args.get("market", "US") or "US").strip().upper()
    ctx.log("jddS snapshot lookup", {"symbol": symbol, "market": market})

    payload = await _fetch(ctx, "market_snapshot", {"symbol": symbol, "market": market})
    status = payload.get("status", "UNAVAILABLE")

    if status != "OK":
        return (
            "\n".join(
                [
                    f"UNAVAILABLE — no stored snapshot for {symbol} in market {market}.",
                    "Data source: JDdS (market data vault). The symbol may not be in the",
                    "universe yet, or the market code is wrong. No price has been invented.",
                ]
            ),
            {"status": "UNAVAILABLE", "symbol": symbol, "market": market, "source": "JDDS"},
        )

    lines = [
        f"Snapshot for {payload.get('symbol', symbol)} — {payload.get('name', '')}",
        f"  Market: {payload.get('exchange', '')} ({payload.get('country', market)})",
        f"  Sector: {payload.get('sector') or 'N/A'}",
        f"  Industry: {payload.get('industry') or 'N/A'}",
        f"  Security type: {payload.get('securityType') or 'N/A'}",
    ]
    price = payload.get("price")
    if price:
        lines += [
            f"  Price: {price.get('price')}",
            f"  Change: {price.get('changePct')}%",
            f"  Market cap: {price.get('marketCap') if price.get('marketCap') is not None else 'N/A'}",
            f"  Volume: {price.get('volume') if price.get('volume') is not None else 'N/A'}",
            f"  P/E: {price.get('peRatio') if price.get('peRatio') is not None else 'N/A'}",
        ]
    else:
        lines.append("  Price: UNAVAILABLE — the asset exists but has no stored price yet.")
    lines.append(f"Data source: JDDS ({payload.get('priceSource', 'n/a')})")
    lines.append(f"Last updated: {payload.get('updatedAt') or 'unknown'}")
    return "\n".join(lines), {"status": "OK", "symbol": symbol, "market": market, "source": "JDDS"}


async def get_fundamentals(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    symbol = str(args.get("symbol", "")).strip().upper()
    payload = await _fetch(ctx, "fundamentals", {"symbol": symbol})
    if payload.get("status") != "OK":
        return f"UNAVAILABLE — no fundamentals stored for {symbol} in JDdS.", {"status": "UNAVAILABLE"}
    return dumps(payload), {"status": "OK", "symbol": symbol}


async def get_news(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query", "") or "")
    payload = await _fetch(ctx, "news", {"query": query})
    items = payload.get("items") or []
    if not items:
        return f"No news found matching {query!r} in JDdS.", {"count": 0, "source": "JDDS"}
    lines = [f"[{i.get('source')}] ({i.get('sentiment')}) {i.get('headline')}\n  {i.get('url', '')}" for i in items]
    return "\n\n".join(lines), {"count": len(items), "source": "JDDS"}


async def get_source_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    payload = await _fetch(ctx, "source_health", {})
    rows = payload.get("rows") or []
    if not rows:
        return "No source health data recorded yet.", {"count": 0}
    lines = [
        f"  {r.get('source')} ({r.get('market')}): {r.get('success')} ok / {r.get('fail')} fail"
        for r in rows
    ]
    return "\n".join(lines), {"count": len(rows)}


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
            description="Read the reliability/health of each JDdS data source per market.",
            input_schema={"type": "object", "properties": {}},
            handler=get_source_health,
            permission="read",
            risk="low",
        )
    )


__all__ = ["register_finance_tools", "DataBridge"]
