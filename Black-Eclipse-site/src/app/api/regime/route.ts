import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { toMarketId } from "@/lib/markets";
import { fetchEconomicCalendar, type CalendarEvent } from "@/lib/economics/calendar";
import { resolveRegimeMarket } from "@/lib/regime/scoring";
import {
  assembleRegime,
  marketNewsRegions,
  scoreMacroSurprises,
  scoreNews,
  scorePriceBreadth,
  scoreVolatility,
  type MacroSurprise,
  type NewsScoredItem,
  type RawComponent,
} from "@/lib/regime/scoring";
import type { RegimeDriver, RegimeResult, RegimeScope } from "@/lib/regime/types";

export const dynamic = "force-dynamic";

// ── Market Regime — explainable sentiment from JDDS only ────────────────────
// One read assembles five components from the JDDS vault (IndexQuote, Asset/
// Price, MacroSeries, NewsItem) plus the existing economics calendar. It never
// fabricates: missing inputs lower confidence; a missing core price/breadth
// input makes the whole reading UNAVAILABLE, never a false neutral.
//
// Scope: `selected` (active user market), `us`, or `global`.

const HEDGES = new Set([
  "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "BNB-USD",
  "GC=F", "SI=F", "CL=F", "BZ=F",
]);

// Freshness budgets per component (ms).
const MAX_AGE = {
  price_breadth: 10 * 60 * 1000, // index quotes: refreshed ~5 min
  volatility: 24 * 60 * 60 * 1000, // VIX daily close
  macro_risk: 30 * 24 * 60 * 60 * 1000, // monthly prints
  news_narrative: 24 * 60 * 60 * 1000, // 24h rolling tape
  positioning: 14 * 24 * 60 * 60 * 1000, // weekly survey
};

// Broad dollar / volatility series used as a fallback risk proxy when a
// market has no local VIX (only for the US-scoped or global reading, where the
// series is meaningful — never to invent a country's volatility).
const VIX_SOURCE = "fred-analytics";
const VIX_SERIES = "VIXCLS";

function benchmarkFor(market: string): string | null {
  switch (market) {
    case "US": return "^GSPC";
    case "IN": return "^NSEI";
    case "UK": return "^FTSE";
    case "DE": return "^GDAXI";
    case "FR": return "^FCHI";
    case "NL": return "^AEX";
    case "JP": return "^N225";
    case "HK": return "^HSI";
    case "CN": return "000001.SS";
    case "KR": return "^KS11";
    case "TW": return "^TWII";
    case "AU": return "^AXJO";
    case "CA": return "^GSPTSE";
    case "BR": return "^BVSP";
    case "MX": return "^MXX";
    case "SA": return "^TASI.SR";
    case "SG": return "^STI";
    case "MY": return "^KLSE";
    case "ID": return "^JKSE";
    case "TH": return "^SET.BK";
    case "CRYPTO": return "BTC-USD";
    default: return null;
  }
}

/** Compute the newest `updatedAt` across a set of IndexQuote-like rows. */
function newestUpdate(rows: Array<{ updatedAt: Date }>): number | null {
  let newest: number | null = null;
  for (const r of rows) {
    const t = r.updatedAt.getTime();
    if (newest === null || t > newest) newest = t;
  }
  return newest;
}

async function buildPriceBreadth(market: string): Promise<{
  component: RawComponent;
  metrics: { breadthUp: number | null; avgChangePct: number | null; count: number };
}> {
  const id = "price_breadth" as const;
  // Index quotes for the market (GLOBAL uses the US benchmark set plus the
  // US sector breadth — the only breadth series JDDS keys by market today).
  const quoteMarket = market === "GLOBAL" ? "US" : market;
  const rows = await prisma.indexQuote.findMany({
    where: { marketId: quoteMarket, price: { gt: 0 } },
    select: { symbol: true, price: true, changePct: true, updatedAt: true },
  });

  const priced = rows.filter(
    (r) => Number.isFinite(r.changePct) && !HEDGES.has(r.symbol),
  );
  if (priced.length === 0) {
    return {
      component: {
        id,
        score: null,
        asOf: null,
        maxAgeMs: MAX_AGE.price_breadth,
        source: "JDDS IndexQuote",
        detail: "No priced index quotes for this market.",
        confidence: 0,
        metrics: { breadthUp: null as unknown as number, avgChangePct: null as unknown as number, count: 0 },
      },
      metrics: { breadthUp: null, avgChangePct: null, count: 0 },
    };
  }

  const avg = priced.reduce((s, r) => s + r.changePct, 0) / priced.length;
  const breadthUp = priced.filter((r) => r.changePct > 0).length / priced.length;

  // Sector breadth from JDDS asset sectors (≥5 constituents per sector).
  let sectorUp: number | null = null;
  if (quoteMarket !== "CRYPTO") {
    const sectorRows = await prisma.asset.findMany({
      where: { marketId: quoteMarket, isActive: true, sector: { not: null } },
      select: { sector: true, price: { select: { changePct: true } } },
      take: 2000,
    });
    const bySector = new Map<string, { sum: number; count: number }>();
    for (const r of sectorRows) {
      if (!r.sector || !r.price) continue;
      const cur = bySector.get(r.sector) || { sum: 0, count: 0 };
      cur.sum += r.price.changePct;
      cur.count += 1;
      bySector.set(r.sector, cur);
    }
    const sectors = [...bySector.values()].filter((v) => v.count >= 5);
    if (sectors.length > 0) {
      sectorUp = sectors.filter((v) => v.sum / v.count > 0).length / sectors.length;
    }
  }

  const score = scorePriceBreadth(avg, breadthUp, sectorUp);
  const asOf = newestUpdate(rows);
  return {
    component: {
      id,
      score,
      asOf,
      maxAgeMs: MAX_AGE.price_breadth,
      source: "JDDS IndexQuote + Asset sectors",
      detail: `Index avg ${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%, ${(breadthUp * 100).toFixed(0)}% of indices up${
        sectorUp != null ? `, ${(sectorUp * 100).toFixed(0)}% of sectors up` : ""
      }.`,
      confidence: 1,
      metrics: { breadthUp, avgChangePct: avg, count: priced.length },
    },
    metrics: { breadthUp, avgChangePct: avg, count: priced.length },
  };
}

async function buildVolatility(market: string): Promise<RawComponent> {
  const id = "volatility" as const;
  // Prefer a local volatility index when the market has one (US/global only).
  const trySymbols = market === "GLOBAL" || market === "US" ? ["^VIX"] : [];
  for (const symbol of trySymbols) {
    const row = await prisma.indexQuote.findFirst({
      where: { symbol, price: { gt: 0 } },
      select: { price: true, updatedAt: true },
    });
    if (row) {
      const score = scoreVolatility(row.price);
      return {
        id,
        score,
        asOf: row.updatedAt.getTime(),
        maxAgeMs: MAX_AGE.volatility,
        source: `JDDS IndexQuote ${symbol}`,
        detail: `${symbol} at ${row.price.toFixed(2)}.`,
        confidence: 1,
      };
    }
  }
  // Fallback: JDDS MacroSeries VIX close (FRED public CSV mirror).
  try {
    const stored = await prisma.macroSeries.findMany({
      where: { source: VIX_SOURCE, seriesKey: { contains: VIX_SERIES } },
      orderBy: { updatedAt: "desc" },
      take: 1,
    });
    if (stored.length > 0) {
      const rows = JSON.parse(stored[0].payload) as Array<{ date: string; value: number | null }>;
      const last = [...rows].reverse().find((r) => r.value != null && Number.isFinite(r.value));
      if (last && last.value != null) {
        const vix = last.value;
        const score = scoreVolatility(vix);
        const ts = Date.parse(last.date);
        return {
          id,
          score,
          asOf: Number.isFinite(ts) ? ts : stored[0].updatedAt.getTime(),
          maxAgeMs: MAX_AGE.volatility,
          source: `JDDS MacroSeries ${VIX_SERIES}`,
          detail: `VIX ${vix.toFixed(2)} as of ${last.date}.`,
          confidence: 0.7,
        };
      }
    }
  } catch {
    /* fall through to unavailable */
  }
  return {
    id,
    score: null,
    asOf: null,
    maxAgeMs: MAX_AGE.volatility,
    source: "JDDS",
    detail: "No volatility index available for this scope.",
    confidence: 0,
  };
}

async function buildMacro(market: string): Promise<{ component: RawComponent; drivers: RegimeDriver[] }> {
  const id = "macro_risk" as const;
  let events: CalendarEvent[] = [];
  try {
    const res = await fetchEconomicCalendar();
    events = res.events ?? [];
  } catch {
    events = [];
  }
  // The calendar covers major economies; for non-US scopes still use it as a
  // global backdrop but only score recent, numeric surprises.
  const now = Date.now();
  const recent = events.filter((e) => {
    const ts = Date.parse(e.date);
    return Number.isFinite(ts) && ts <= now && now - ts <= MAX_AGE.macro_risk;
  });

  const num = (v: string | null): number | null => {
    if (v == null) return null;
    const cleaned = v.replace(/[%,$]/g, "").replace(/^\((.*)\)$/, "-$1").trim();
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : null;
  };

  const surprises: MacroSurprise[] = [];
  const drivers: RegimeDriver[] = [];
  for (const e of recent) {
    const actual = num(e.actual);
    const forecast = num(e.forecast);
    if (actual == null || forecast == null) continue;
    // Higher-than-forecast inflation is risk-off; growth/jobs higher is risk-on.
    const t = e.title.toLowerCase();
    const inflation = /cpi|inflation|ppi|hicp|price/.test(t);
    const polarity: 1 | -1 = inflation ? -1 : 1;
    surprises.push({ actual, forecast, importance: e.importance, polarity });
    drivers.push({
      headline: `${e.country} ${e.title}: actual ${e.actual} vs forecast ${e.forecast}`,
      source: "Economic calendar",
      sentiment: (actual - forecast) * polarity > 0 ? "bullish" : (actual - forecast) * polarity < 0 ? "bearish" : "neutral",
      at: Date.parse(e.date),
    });
  }

  const score = scoreMacroSurprises(surprises);
  const asOf = recent.length > 0
    ? Math.max(...recent.map((e) => Date.parse(e.date)).filter(Number.isFinite))
    : null;

  return {
    component: {
      id,
      score,
      asOf,
      maxAgeMs: MAX_AGE.macro_risk,
      source: "JDDS economics calendar",
      detail:
        surprises.length > 0
          ? `${surprises.length} recent release${surprises.length === 1 ? "" : "s"} scored vs forecast.`
          : "No recent numeric releases with forecast/actual to score.",
      confidence: surprises.length > 0 ? 0.6 : 0,
    },
    drivers,
  };
}

async function buildNews(market: string): Promise<{ component: RawComponent; drivers: RegimeDriver[] }> {
  const id = "news_narrative" as const;
  const now = Date.now();
  const since = new Date(now - 48 * 3600 * 1000);
  const rows = await prisma.newsItem.findMany({
    where: { timestamp: { gte: since } },
    orderBy: { timestamp: "desc" },
    take: 400,
    select: { source: true, headline: true, url: true, sentiment: true, tier: true, region: true, ticker: true, timestamp: true, category: true, dedupKey: true },
  });

  if (rows.length === 0) {
    return {
      component: {
        id,
        score: null,
        asOf: null,
        maxAgeMs: MAX_AGE.news_narrative,
        source: "JDDS NewsItem",
        detail: "No ingested news in the last 48h.",
        confidence: 0,
      },
      drivers: [],
    };
  }

  const regions = new Set(marketNewsRegions(market));
  const marketRelevant = rows.filter((r) => !r.region || regions.has(r.region.toUpperCase()));

  // Deduplicate by dedupKey AND by a normalized headline so a syndicated story
  // counted once, then score recency/tier/relevance weighted.
  const seenKey = new Set<string>();
  const seenHeadline = new Set<string>();
  const items: NewsScoredItem[] = [];
  for (const r of marketRelevant) {
    const normHeadline = r.headline.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
    if (seenKey.has(r.dedupKey) || seenHeadline.has(normHeadline)) continue;
    seenKey.add(r.dedupKey);
    seenHeadline.add(normHeadline);
    // Relevance: market/economic categories are on-topic; a ticker match is
    // stronger still when the scope is a country (heuristic, capped at 1).
    const cat = (r.category ?? "").toUpperCase();
    const onMarket = cat === "MARKETS" || cat === "ECONOMIC" || cat === "CENTRAL BANKS" || cat === "INFLATION";
    const relevance = (onMarket ? 1 : 0.7) * (r.ticker ? 1 : 0.9);
    items.push({
      sentiment: (r.sentiment as NewsScoredItem["sentiment"]) ?? "neutral",
      tier: r.tier,
      at: r.timestamp.getTime(),
      relevance,
    });
  }

  const score = scoreNews(items, now);
  const drivers: RegimeDriver[] = marketRelevant.slice(0, 5).map((r) => ({
    headline: r.headline,
    source: r.source,
    url: r.url,
    sentiment: (r.sentiment as RegimeDriver["sentiment"]) ?? "neutral",
    at: r.timestamp.getTime(),
  }));

  const asOf = rows.length > 0 ? rows[0].timestamp.getTime() : null;
  const tiers = new Set(rows.map((r) => r.tier ?? 3));
  return {
    component: {
      id,
      score,
      asOf,
      maxAgeMs: MAX_AGE.news_narrative,
      source: "JDDS NewsItem (tier-weighted, recency-decayed)",
      detail: `${items.length} deduped market headlines across ${tiers.size} source tier${tiers.size === 1 ? "" : "s"}.`,
      confidence: Math.min(1, items.length / 20),
    },
    drivers,
  };
}

async function buildPositioning(): Promise<RawComponent> {
  // Optional, low-frequency, potentially contrarian input. AAII sentiment is
  // not wired to JDDS today, so this is honestly UNAVAILABLE rather than faked.
  return {
    id: "positioning",
    score: null,
    asOf: null,
    maxAgeMs: MAX_AGE.positioning,
    source: "JDDS (AAII not ingested)",
    detail:
      "No positioning survey (e.g. AAII) ingested. Positioned as a slow, potentially contrarian input when available.",
    confidence: 0,
  };
}

// ── In-memory SWR cache of the raw components ────────────────────────────────
// Building the five components reads index quotes, up to 2000 asset-sector rows,
// 400 news rows and the economics calendar on EVERY request (~0.8s of synchronous
// better-sqlite3 work on the single SQLite thread). Regime inputs carry freshness
// budgets of 10 min (price breadth) up to 30 days, so a short TTL sits well
// inside their tolerance. Only the COMPONENTS are cached; `assembleRegime()`
// re-runs per request so `builtAt` and every derived age stay current — the UI's
// freshness labels never misreport how old a reading is.
const COMPONENT_TTL_MS = 60_000;

type RegimeComponents = { raw: RawComponent[]; drivers: RegimeDriver[] };
const componentCache = new Map<string, { t: number; data: RegimeComponents }>();
const componentRebuilding = new Set<string>();

async function buildComponents(market: string): Promise<RegimeComponents> {
  const [price, volatility, macro, news, positioning] = await Promise.all([
    buildPriceBreadth(market),
    buildVolatility(market),
    buildMacro(market),
    buildNews(market),
    buildPositioning(),
  ]);
  return {
    raw: [price.component, volatility, macro.component, news.component, positioning],
    drivers: [...news.drivers, ...macro.drivers].slice(0, 6),
  };
}

function startComponentRebuild(market: string) {
  if (componentRebuilding.has(market)) return;
  componentRebuilding.add(market);
  buildComponents(market)
    .then((data) => componentCache.set(market, { t: Date.now(), data }))
    .catch((err) => console.error("[api/regime] component rebuild error:", err))
    .finally(() => componentRebuilding.delete(market));
}

async function getComponents(market: string): Promise<RegimeComponents> {
  const hit = componentCache.get(market);
  if (hit) {
    if (Date.now() - hit.t < COMPONENT_TTL_MS) return hit.data;
    startComponentRebuild(market); // serve stale, refresh quietly
    return hit.data;
  }
  const data = await buildComponents(market);
  componentCache.set(market, { t: Date.now(), data });
  return data;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const scopeParam = searchParams.get("scope");
  const scope: RegimeScope =
    scopeParam === "us" || scopeParam === "global" || scopeParam === "selected" ? scopeParam : "selected";
  const selectedMarket = toMarketId((searchParams.get("market") || "US").toUpperCase());
  const market = scope === "global" ? "GLOBAL" : resolveRegimeMarket(scope, selectedMarket);

  try {
    const components = await getComponents(market);

    const result: RegimeResult = assembleRegime({
      scope,
      market,
      benchmarkSymbol: benchmarkFor(market === "GLOBAL" ? "US" : market),
      raw: components.raw,
      drivers: components.drivers,
    });

    return NextResponse.json(result);
  } catch (err) {
    console.error("[api/regime] error:", err instanceof Error ? err.message : err);
    // Honest UNAVAILABLE — never a fabricated reading.
    const result = assembleRegime({
      scope,
      market,
      raw: [
        { id: "price_breadth", score: null, asOf: null, maxAgeMs: MAX_AGE.price_breadth, source: "JDDS", detail: "Regime read failed.", confidence: 0 },
      ],
    });
    return NextResponse.json(result, { status: 500 });
  }
}
