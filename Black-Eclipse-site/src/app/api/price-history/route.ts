import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { fetchPsxIndexChart } from "@/lib/scraper/fetchers/psx-index";
import { resolveIndex } from "@/lib/indices";
import { ttlForInterval } from "@/lib/chart/price-history-ttl";
import { observationMeta } from "@/lib/chart/observation-freshness";
import { fetchYahooChartSeries, yahooChartCandidates, type Bar } from "@/lib/scraper/yahoo-chart";

export const dynamic = "force-dynamic";

// ── SWR cache (in-memory + Prisma-persisted last-good) ────────────────────────
// Yahoo chart fetches take 2–45s; every fresh user request re-hit upstream.
// Serve cached instantly and refresh in the background, mirroring /api/forex.
//
// The TTL is TIMEFRAME-AWARE (see `ttlForInterval`): a 1-minute series is stale
// within seconds, so a flat 10-minute cache made intraday charts show ~10–20-
// minute-old candles (client cache + this one). Daily/weekly/monthly keep the
// long TTL because a day bar genuinely does not change intraday.
const historyCache = new Map<string, { t: number; payload: unknown }>();
const historyInFlight = new Map<string, Promise<unknown>>();
const PERSIST_PREFIX = "api_cache:price-history:";

function cacheKey(symbol: string, market: string, range: string, interval: string) {
  return `${symbol}|${market}|${range}|${interval}`;
}

async function persistHistory(key: string, data: unknown) {
  try {
    await prisma.systemConfig.upsert({
      where: { key: PERSIST_PREFIX + key },
      update: { value: JSON.stringify(data) },
      create: { key: PERSIST_PREFIX + key, value: JSON.stringify(data) },
    });
  } catch { /* best-effort */ }
}

async function loadPersistedHistory(key: string): Promise<unknown | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: PERSIST_PREFIX + key } });
    if (!row?.value) return null;
    const parsed = JSON.parse(row.value);
    if (parsed && Array.isArray(parsed.series) && parsed.series.length >= 2) return parsed;
  } catch { /* ignore */ }
  return null;
}

function startBackgroundRefresh(key: string, symbol: string, market: string, range: string, interval: string) {
  if (historyInFlight.has(key)) return;
  const def = resolveIndex(symbol);
  const currency = def?.currency || MARKET_CURRENCY[market] || "$";
  const p = (async () => {
    try {
      if (def?.provider === "psx") {
        const bars = await fetchPsxIndexChart(symbol);
        if (bars.length >= 2) {
          const payload = buildPayload(symbol, currency, bars, interval, { ticker: symbol, source: "psx" });
          historyCache.set(key, { t: Date.now(), payload });
          void persistHistory(key, payload);
        }
        return;
      }
      for (const ticker of yahooChartCandidates(symbol, market)) {
        const chart = await fetchYahooChartSeries(ticker, range, interval);
        if (chart) {
          const payload = buildPayload(symbol, currency, chart.bars, interval, { ticker, source: "yfinance" });
          historyCache.set(key, { t: Date.now(), payload });
          void persistHistory(key, payload);
          return;
        }
      }
    } finally {
      historyInFlight.delete(key);
    }
  })();
  historyInFlight.set(key, p);
}

/** Currency for a symbol: the index's own, else the resolved market's. */
function currencyFor(def: ReturnType<typeof resolveIndex>, market: string): string {
  return def?.currency || MARKET_CURRENCY[market] || "$";
}

// Other markets to retry when the hinted one has no series. Ordered by how
// likely they are to hold a foreign listing; excludes PSX (needs .KA handling
// this route already applies) and the pseudo-markets.
const DISCOVERY_MARKETS = ["US", "IN", "UK", "JP", "DE", "FR", "NL", "CA", "AU", "KR", "TW", "HK", "CN", "SG", "CRYPTO"];

/**
 * Find the real markets that list `symbol`, from JDDS. One indexed query —
 * far cheaper and more accurate than blind-probing Yahoo with every exchange
 * suffix. Markets are returned in discovery order with the hint's match omitted.
 */
async function discoverMarkets(symbol: string, alreadyTried: string): Promise<string[]> {
  try {
    const rows = await prisma.asset.findMany({
      where: { symbol, isActive: true, price: { isNot: null } },
      select: { marketId: true, securityType: true },
      take: 40,
    });
    if (rows.length === 0) return [];
    const present = new Set(rows.map(r => r.marketId));
    // Prefer rows that look like the primary listing (a plain "Stock").
    const ranked = [...present].sort((a, b) => {
      const rankOf = (m: string) => {
        const r = rows.find(x => x.marketId === m);
        return r?.securityType && /stock/i.test(r.securityType) ? 0 : 1;
      };
      return rankOf(a) - rankOf(b) || DISCOVERY_MARKETS.indexOf(a) - DISCOVERY_MARKETS.indexOf(b);
    });
    return ranked.filter(m => m !== alreadyTried).slice(0, 4);
  } catch {
    return [];
  }
}


/** An honest "no data" payload: explicitly unavailable, never a fabricated line. */
function unavailablePayload(symbol: string, interval = "1d") {
  return {
    symbol,
    points: [],
    series: [],
    source: "none",
    observationTime: null,
    retrievedAt: new Date().toISOString(),
    freshness: "unavailable" as const,
    stale: true,
    ageMs: null,
    interval,
  };
}

function buildPayload(
  symbol: string,
  currency: string,
  bars: Bar[],
  interval: string,
  extra: { ticker: string; source: "yfinance" | "psx" },
) {
  return {
    symbol,
    ticker: extra.ticker,
    currency,
    points: bars.map((b) => b.close),
    series: bars,
    interval,
    perf: {
      week: perfOver(bars, 5),
      month: perfOver(bars, 21),
      quarter: perfOver(bars, 63),
    },
    source: extra.source,
    // Observation envelope: when the newest bar was observed, when we produced
    // this payload, and whether it may be shown as current. A chart must render
    // a stale series as stale, never as live.
    ...observationMeta(bars, interval),
  };
}

/**
 * Serve a PSX benchmark (KSE-100 / KSE-30 / KMI-30) from the exchange's own
 * historical endpoint. Yahoo dropped these, so this is the only real source;
 * when it has nothing we return an empty series (an honest UNAVAILABLE) rather
 * than a fabricated line.
 */
async function respondWithPsxIndex(symbol: string, currency: string, interval: string) {
  const key = cacheKey(symbol, "PK", "6mo", interval);
  const cached = historyCache.get(key);
  if (cached && Date.now() - cached.t < ttlForInterval(interval)) {
    return NextResponse.json(cached.payload);
  }

  const bars = await fetchPsxIndexChart(symbol);
  if (bars.length >= 2) {
    const payload = buildPayload(symbol, currency, bars, interval, { ticker: symbol, source: "psx" });
    historyCache.set(key, { t: Date.now(), payload });
    void persistHistory(key, payload);
    return NextResponse.json(payload);
  }

  const persisted = await loadPersistedHistory(key);
  if (persisted) return NextResponse.json(persisted);

  return NextResponse.json(unavailablePayload(symbol, interval));
}

// GET /api/price-history?symbol=OGDC&market=PK
//
// Returns a REAL daily OHLCV series (default 3 months) for the stock detail
// charts, plus derived performance stats (1W / 1M / 3M % change).
//
// Resolution order:
//   0. Index registry — a known index alias (`SPX` → `^GSPC`) resolves to its
//      real provider. Yahoo-backed indices fetch normally; the PSX benchmarks
//      (Yahoo dropped ^KSE100) go to the exchange's historical endpoint.
//   1. Yahoo chart HTTP API (direct fetch with a browser UA — no Python).
//      The installed yfinance lib (1.5.1) 404s on PSX tickers, but the raw
//      chart endpoint serves them under the .KA (Karachi) suffix, so PK gets
//      a suffix fallback chain: <sym>.PSX → <sym>.KA → bare.
//   2. persisted Price row snapshot (single point; series = [prevClose, price]).
//
// Response: {
//   symbol, currency, points: number[], series: { date, open, high, low, close, volume }[],
//   perf: { week?: number, month?: number, quarter?: number },
//   source: "yfinance" | "psx" | "snapshot"
// }
//
// The Yahoo fetch + ticker-candidate resolution live in `@/lib/scraper/yahoo-chart`
// so the on-demand live-quote read-through shares exactly one implementation.

// % change over the last `back` trading rows (null when not enough history).
function perfOver(bars: Bar[], back: number): number | undefined {
  if (bars.length <= back) return undefined;
  const last = bars[bars.length - 1].close;
  const base = bars[bars.length - 1 - back].close;
  if (!base || base <= 0) return undefined;
  return +(((last - base) / base) * 100).toFixed(2);
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = (searchParams.get("symbol") || "").trim().toUpperCase();
  const market = (searchParams.get("market") || "US").trim().toUpperCase();
  const range = (searchParams.get("range") || "3mo").trim().toLowerCase();
  const interval = (searchParams.get("interval") || "1d").trim().toLowerCase();

  if (!symbol) {
    return NextResponse.json(unavailablePayload(symbol, interval));
  }

  // A resolved index knows its own home market + currency, so a bare `^FTSE`
  // charts with GBP (not the caller's default US/$) and the PSX benchmarks are
  // routed to their own provider.
  const def = resolveIndex(symbol);
  // `^KSE100` etc. — Yahoo has no PSX index; use the exchange endpoint.
  if (def?.provider === "psx") {
    return respondWithPsxIndex(symbol, def.currency, interval);
  }

  const preferred = def?.market || market;
  const key = cacheKey(symbol, preferred, range, interval);

  // 0) SWR: fresh cache serves instantly; stale cache serves + background refresh.
  const ttl = ttlForInterval(interval);
  const cached = historyCache.get(key);
  if (cached && Date.now() - cached.t < ttl) {
    return NextResponse.json(cached.payload);
  }
  if (cached) {
    startBackgroundRefresh(key, symbol, preferred, range, interval);
    return NextResponse.json(cached.payload);
  }

  // 1) Real series from the Yahoo chart API — try the hinted market's candidates.
  for (const ticker of yahooChartCandidates(symbol, preferred)) {
    const chart = await fetchYahooChartSeries(ticker, range, interval);
    if (chart) {
      const payload = buildPayload(symbol, currencyFor(def, preferred), chart.bars, interval, {
        ticker, source: "yfinance",
      });
      historyCache.set(key, { t: Date.now(), payload });
      void persistHistory(key, payload);
      return NextResponse.json(payload);
    }
  }

  // 1a) The caller's `market` is a HINT, not a fact. Clients that don't know a
  //     symbol's home market (the fund workspace before this fix) sent US for
  //     everything, so an Indian holding was requested without its `.NS` suffix
  //     and silently produced no series. Ask JDDS which markets list the symbol
  //     — one cheap indexed lookup — and retry with the real one.
  for (const m of await discoverMarkets(symbol, preferred)) {
    for (const ticker of yahooChartCandidates(symbol, m)) {
      const chart = await fetchYahooChartSeries(ticker, range, interval);
      if (chart) {
        const payload = buildPayload(symbol, currencyFor(def, m), chart.bars, interval, {
          ticker, source: "yfinance",
        });
        historyCache.set(key, { t: Date.now(), payload });
        void persistHistory(key, payload);
        return NextResponse.json(payload);
      }
    }
  }

  // 1b) No live series — try the persisted last-good snapshot before giving up.
  const persisted = await loadPersistedHistory(key);
  if (persisted) {
    historyCache.set(key, { t: Date.now() - ttl / 2, payload: persisted });
    startBackgroundRefresh(key, symbol, market, range, interval);
    return NextResponse.json(persisted);
  }

  // 2) Bridge unavailable / no history — fall back to the DB snapshot.
  //    Search across markets too: the snapshot is keyed by (symbol, marketId)
  //    and the caller's market may be the same wrong hint we corrected above.
  try {
    const byHint = await prisma.asset.findFirst({
      where: { symbol, marketId: preferred, isActive: true },
      select: { price: { select: { price: true, previousClose: true, updatedAt: true } }, marketId: true },
    });
    const asset = byHint ?? await prisma.asset.findFirst({
      where: { symbol, isActive: true, price: { isNot: null } },
      select: { price: { select: { price: true, previousClose: true, updatedAt: true } }, marketId: true },
    });
    if (asset?.price && asset.price.price > 0) {
      const last = asset.price.price;
      const prev = asset.price.previousClose ?? last;
      // The snapshot is the LAST KNOWN observation, not a live series. Date both
      // points from its real `updatedAt` (never "now") and attach the freshness
      // envelope so the caller can render it as stale/historical. Serving a
      // months-old close under today's date was the defect that let a stale JDDS
      // price sit next to a live header (the OGDC-class split).
      const observedMs = asset.price.updatedAt?.getTime?.() ?? Date.now();
      const observedIso = new Date(observedMs).toISOString().slice(0, 10);
      const prevIso = new Date(observedMs - 86400000).toISOString().slice(0, 10);
      const meta = observationMeta([{ date: observedIso }], interval);
      return NextResponse.json({
        symbol,
        currency: currencyFor(def, asset.marketId || preferred),
        points: [prev, last],
        series: [
          { date: prevIso, open: prev, high: prev, low: prev, close: prev, volume: null },
          { date: observedIso, open: prev, high: last, low: prev, close: last, volume: null },
        ],
        perf: { week: undefined, month: undefined, quarter: undefined },
        source: "snapshot",
        ...meta,
      });
    }
  } catch { /* ignore */ }

  return NextResponse.json(unavailablePayload(symbol, interval));
}