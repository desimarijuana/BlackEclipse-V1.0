// ─── JDdS data bridge ────────────────────────────────────────────────────────
// The ONLY place the agentic runtime reaches JDdS. The Python tools request a
// capability by name; this module performs the Prisma query and returns plain,
// provenance-carrying JSON. It is read-only by construction — there is no write
// path here.
//
// This exists so the agentic side (Python) owns tools/agents/events/memory while
// market data stays in the single Node data layer.

import { prisma } from "@/lib/db";
import type { DataCapability } from "./types";

export interface DataBridgeResult {
  status: "OK" | "UNAVAILABLE";
  [key: string]: unknown;
}

function unavailable(reason?: string): DataBridgeResult {
  return { status: "UNAVAILABLE", ...(reason ? { error: reason } : {}) };
}

export async function fetchCapability(
  capability: DataCapability,
  params: Record<string, unknown>
): Promise<DataBridgeResult> {
  switch (capability) {
    case "market_snapshot":
      return marketSnapshot(params);
    case "fundamentals":
      return fundamentals(params);
    case "news":
      return news(params);
    case "source_health":
      return sourceHealth();
    default:
      return unavailable(`Unknown capability: ${String(capability)}`);
  }
}

async function marketSnapshot(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  const market = String(params.market ?? "US").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");

  const asset = await prisma.asset.findFirst({
    where: { symbol, market: { country: market } },
    include: { price: true, market: true },
  });
  if (!asset) return unavailable("symbol not in the JDdS universe");

  return {
    status: "OK",
    symbol: asset.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    country: asset.market.country,
    exchange: asset.market.exchange,
    priceSource: asset.price?.source ?? null,
    updatedAt: asset.price?.updatedAt?.toISOString() ?? null,
    price: asset.price
      ? {
          price: asset.price.price,
          changePct: asset.price.changePct,
          marketCap: asset.price.marketCap,
          volume: asset.price.volume,
          peRatio: asset.price.peRatio,
        }
      : null,
  };
}

async function fundamentals(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const asset = await prisma.asset.findFirst({
    where: { symbol },
    include: { price: true, market: true },
  });
  if (!asset) return unavailable("symbol not found in JDdS");
  return {
    status: "OK",
    symbol: asset.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: asset.assetClass,
    market: asset.market.exchange,
    country: asset.market.country,
    price: asset.price?.price ?? null,
  };
}

async function news(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").toLowerCase().trim();
  const where = query
    ? { OR: [{ headline: { contains: query } }, { summary: { contains: query } }] }
    : {};
  const items = await prisma.newsItem.findMany({
    where,
    orderBy: { timestamp: "desc" },
    take: 10,
  });
  return {
    status: "OK",
    items: items.map((i) => ({
      source: i.source,
      headline: i.headline,
      summary: i.summary,
      sentiment: i.sentiment,
      url: i.url,
      timestamp: i.timestamp.toISOString(),
    })),
  };
}

async function sourceHealth(): Promise<DataBridgeResult> {
  const rows = await prisma.sourceHealth.groupBy({
    by: ["source", "market"],
    _sum: { successCount: true, failCount: true },
    _max: { lastStatus: true },
  });
  return {
    status: "OK",
    rows: rows.map((r) => ({
      source: r.source,
      market: r.market,
      success: r._sum.successCount ?? 0,
      fail: r._sum.failCount ?? 0,
      lastStatus: r._max.lastStatus,
    })),
  };
}
