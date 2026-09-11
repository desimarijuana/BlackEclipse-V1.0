import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { yahooSymbol } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

// ── SWR cache (in-memory + Prisma-persisted last-good) ────────────────────────
// Yahoo chart fetches take 2–45s; every fresh user request re-hit upstream.
// Serve cached instantly and refresh in the background, mirroring /api/forex.
const HISTORY_TTL_MS = 10 * 60 * 1000; // daily data → 10min is plenty fresh
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
  const p = (async () => {
    try {
      for (const ticker of tickerCandidates(symbol, market)) {
        const chart = await fetchYahooChart(ticker, range, interval);
        if (chart) {
          const points = chart.bars.map((b) => b.close);
          const payload = {
            symbol, ticker,
            currency: MARKET_CURRENCY[market] || "$",
            points,
            series: chart.bars,
            interval,
            perf: {
              week: perfOver(chart.bars, 5),
              month: perfOver(chart.bars, 21),
              quarter: perfOver(chart.bars, 63),
            },
            source: "yfinance",
          };
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

// GET /api/price-history?symbol=OGDC&market=PK
//
// Returns a REAL daily OHLCV series (default 3 months) for the stock detail
// charts, plus derived performance stats (1W / 1M / 3M % change).
//
// Resolution order:
//   1. Yahoo chart HTTP API (direct fetch with a browser UA — no Python).
//      The installed yfinance lib (1.5.1) 404s on PSX tickers, but the raw
//      chart endpoint serves them under the .KA (Karachi) suffix, so PK gets
//      a suffix fallback chain: <sym>.PSX → <sym>.KA → bare.
//   2. persisted Price row snapshot (single point; series = [prevClose, price]).
//
// Response: {
//   symbol, currency, points: number[], series: { date, open, high, low, close, volume }[],
//   perf: { week?: number, month?: number, quarter?: number },
//   source: "yfinance" | "snapshot"
// }

interface Bar {
  date: string;
  time?: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

// Candidate Yahoo tickers to try, in order, for one symbol+market.
function tickerCandidates(symbol: string, market: string): string[] {
  const candidates = [yahooSymbol(symbol, market)];
  if (market === "PK") {
    // Yahoo serves PSX under the KAR exchange (.KA); the .PSX suffix 404s.
    const bare = symbol.replace(/\.PSX$/i, "");
    if (!candidates.includes(`${bare}.KA`)) candidates.push(`${bare}.KA`);
    if (!candidates.includes(bare)) candidates.push(bare);
  }
  const bare = symbol.replace(/\.(PSX|NS|BO|SS|SZ|BJ|TW|T|HK|KS|KQ|SI|KL|AX|L|DE|PA|AS|TO|SA|SR|AE|JO|CA|NG|ME|IS|JK|BK|VN)$/i, "");
  if (bare !== symbol && !candidates.includes(bare)) candidates.push(bare);
  return candidates;
}

async function fetchYahooChart(ticker: string, range: string, interval = "1d"): Promise<{ bars: Bar[] } | null> {
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}` +
    `?range=${range}&interval=${interval}&includePrePost=false`;
  try {
    const res = await fetch(url, {
      headers: {
        // The chart endpoint 404s for some exchanges without a browser UA.
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(20000),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const json = (await res.json()) as {
      chart?: {
        result?: Array<{
          timestamp?: number[];
          indicators?: { quote?: Array<{ open?: (number | null)[]; high?: (number | null)[]; low?: (number | null)[]; close?: (number | null)[]; volume?: (number | null)[] }> };
        }>;
      };
    };
    const result = json.chart?.result?.[0];
    const ts = result?.timestamp;
    const q = result?.indicators?.quote?.[0];
    if (!ts || !q || ts.length === 0) return null;

    const bars: Bar[] = [];
    for (let i = 0; i < ts.length; i++) {
      const close = q.close?.[i];
      if (close == null || !Number.isFinite(close) || close <= 0) continue;
      bars.push({
        date: new Date(ts[i] * 1000).toISOString().slice(0, 10),
        time: ts[i] * 1000,
        open: q.open?.[i] ?? null,
        high: q.high?.[i] ?? null,
        low: q.low?.[i] ?? null,
        close,
        volume: q.volume?.[i] ?? null,
      });
    }
    return bars.length >= 2 ? { bars } : null;
  } catch {
    return null;
  }
}

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
    return NextResponse.json({ points: [], series: [], source: "none" });
  }

  const currency = MARKET_CURRENCY[market] || "$";
  const key = cacheKey(symbol, market, range, interval);

  // 0) SWR: fresh cache serves instantly; stale cache serves + background refresh.
  const cached = historyCache.get(key);
  if (cached && Date.now() - cached.t < HISTORY_TTL_MS) {
    return NextResponse.json(cached.payload);
  }
  if (cached) {
    startBackgroundRefresh(key, symbol, market, range, interval);
    return NextResponse.json(cached.payload);
  }

  // 1) Real series from the Yahoo chart API — try each ticker candidate.
  for (const ticker of tickerCandidates(symbol, market)) {
    const chart = await fetchYahooChart(ticker, range, interval);
    if (chart) {
      const points = chart.bars.map((b) => b.close);
      const payload = {
        symbol,
        ticker,
        currency,
        points,
        series: chart.bars,
        interval,
        perf: {
          week: perfOver(chart.bars, 5),
          month: perfOver(chart.bars, 21),
          quarter: perfOver(chart.bars, 63),
        },
        source: "yfinance",
      };
      historyCache.set(key, { t: Date.now(), payload });
      void persistHistory(key, payload);
      return NextResponse.json(payload);
    }
  }

  // 1b) No live series — try the persisted last-good snapshot before giving up.
  const persisted = await loadPersistedHistory(key);
  if (persisted) {
    historyCache.set(key, { t: Date.now() - HISTORY_TTL_MS / 2, payload: persisted });
    startBackgroundRefresh(key, symbol, market, range, interval);
    return NextResponse.json(persisted);
  }

  // 2) Bridge unavailable / no history — fall back to the DB snapshot.
  try {
    const asset = await prisma.asset.findFirst({
      where: { symbol, marketId: market, isActive: true },
      select: { price: { select: { price: true, previousClose: true } } },
    });
    if (asset?.price && asset.price.price > 0) {
      const last = asset.price.price;
      const prev = asset.price.previousClose ?? last * 0.99;
      const points = [prev, last];
      return NextResponse.json({
        symbol,
        currency,
        points,
        series: [
          {
            date: new Date(Date.now() - 86400000).toISOString().slice(0, 10),
            open: prev, high: prev, low: prev, close: prev, volume: null,
          },
          {
            date: new Date().toISOString().slice(0, 10),
            open: prev, high: last, low: prev, close: last, volume: null,
          },
        ],
        perf: { week: undefined, month: undefined, quarter: undefined },
        source: "snapshot",
      });
    }
  } catch { /* ignore */ }

  return NextResponse.json({ symbol, points: [], series: [], source: "none" });
}