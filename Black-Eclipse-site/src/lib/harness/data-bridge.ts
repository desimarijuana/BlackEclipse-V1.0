// ─── JDdS data bridge ────────────────────────────────────────────────────────
// The ONLY place the agentic runtime reaches JDdS. The Python tools request a
// capability by name; this module performs the Prisma query and returns plain,
// provenance-carrying JSON. It is read-only by construction — there is no write
// path here.
//
// This exists so the agentic side (Python) owns tools/agents/events/memory while
// market data stays in the single Node data layer.

import { prisma } from "@/lib/db";
import { fetchQuoteWithFallback } from "@/lib/scraper/fetchers";
import { fetchYahooBatchRaw } from "@/lib/scraper/fetchers/yfinance";
import { normalizeEconomicSeries, sortByDate } from "@/lib/economics/fetch";
import { getSource } from "@/lib/economics/sources";
import { webSearch, fetchWebPage } from "@/lib/web-research";
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
    case "live_quote":
      return liveQuote(params);
    case "price_history":
      return priceHistory(params);
    case "macro_series":
      return macroSeries(params);
    case "web_search":
      return webSearchCapability(params);
    case "web_fetch":
      return webFetchCapability(params);
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

// ── Live structured providers (Phase 2) ─────────────────────────────────────
// Reuse the existing scraper fallback chain and Yahoo bridge — NOT a new
// market-data system. The Python retrieval layer decides *when* to call these.

async function liveQuote(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const market = String(params.market ?? "US").trim().toUpperCase();
  try {
    const result = await fetchQuoteWithFallback(symbol, market);
    if (result.status !== "ok" || !result.quote) {
      return unavailable(result.error || `no live quote for ${symbol} (${result.status})`);
    }
    const q = result.quote;
    return {
      status: "OK",
      symbol,
      market,
      provider: result.source ?? "scraper",
      currency: undefined,
      price: {
        price: q.price,
        changePct: q.changePct,
        volume: q.volume ?? null,
        marketCap: q.marketCap ?? null,
      },
      asOf: new Date().toISOString(),
    };
  } catch (err) {
    return unavailable(err instanceof Error ? err.message : "live quote failed");
  }
}

async function priceHistory(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const market = String(params.market ?? "US").trim().toUpperCase();
  const range = String(params.range ?? "1y").trim().toLowerCase();
  const interval = String(params.period ?? params.interval ?? "1d").trim().toLowerCase();
  // Prefer the batched Yahoo bridge (one python process), which returns a full
  // OHLCV series; fall back to the existing chart helper when the bridge is off.
  try {
    const data = await fetchYahooBatchRaw([symbol], market, interval, range);
    const key = Object.keys(data.history ?? {})[0];
    const rows = key ? data.history?.[key] : undefined;
    if (Array.isArray(rows) && rows.length >= 2) {
      return { status: "OK", symbol, market, interval, provider: "yfinance", series: rows, asOf: rows[rows.length - 1]?.date ?? null };
    }
  } catch {
    /* fall through */
  }
  return unavailable(`no historical series for ${symbol} (${market})`);
}

async function macroSeries(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const sourceId = String(params.source ?? "fred-analytics").trim();
  const series = String(params.series ?? params.seriesId ?? "").trim();
  const source = getSource(sourceId);
  if (!source) return unavailable(`unknown macro source: ${sourceId}`);
  if (source.keyRequired && source.keyEnv && !process.env[source.keyEnv]) {
    return unavailable(`macro source ${sourceId} requires ${source.keyEnv}`);
  }
  try {
    const fetchParams: Record<string, string> = {};
    for (const c of source.controls) {
      const v = params[c.name];
      if (typeof v === "string" && v) fetchParams[c.name] = v;
      else if (c.defaultValue) fetchParams[c.name] = c.defaultValue;
    }
    if (series) {
      const seriesControl = source.controls.find((c) => c.name === "series" || c.name === "seriesId");
      if (seriesControl) fetchParams[seriesControl.name] = series;
    }
    const raw = await source.fetch(fetchParams);
    const rows = sortByDate(normalizeEconomicSeries(raw, sourceId));
    if (rows.length === 0) return unavailable(`macro source ${sourceId} returned no observations`);
    return {
      status: "OK",
      source: sourceId,
      seriesKey: series || source.label,
      rows,
      asOf: rows[rows.length - 1]?.date ?? null,
    };
  } catch (err) {
    return unavailable(err instanceof Error ? err.message : "macro fetch failed");
  }
}

// ── Web research (shared transport; no second search system) ────────────────

async function webSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailable("query is required");
  const limit = Number(params.limit ?? 8);
  const results = await webSearch(query, Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 15) : 8);
  if (results.length === 0) return unavailable("no results");
  return { status: "OK", query, results };
}

async function webFetchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const url = String(params.url ?? "").trim();
  if (!url) return unavailable("url is required");
  const page = await fetchWebPage(url);
  if (!page) return unavailable("page could not be retrieved or was not usable HTML");
  return { status: "OK", url: page.url, title: page.title, text: page.text, bytes: page.bytes };
}
