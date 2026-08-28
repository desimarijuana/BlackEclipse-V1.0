import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { yahooSymbol } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

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

async function fetchYahooChart(ticker: string, range: string): Promise<{ bars: Bar[] } | null> {
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}` +
    `?range=${range}&interval=1d&includePrePost=false`;
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

  if (!symbol) {
    return NextResponse.json({ points: [], series: [], source: "none" });
  }

  const currency = MARKET_CURRENCY[market] || "$";

  // 1) Real series from the Yahoo chart API — try each ticker candidate.
  for (const ticker of tickerCandidates(symbol, market)) {
    const chart = await fetchYahooChart(ticker, range);
    if (chart) {
      const points = chart.bars.map((b) => b.close);
      return NextResponse.json({
        symbol,
        ticker,
        currency,
        points,
        series: chart.bars,
        perf: {
          week: perfOver(chart.bars, 5),
          month: perfOver(chart.bars, 21),
          quarter: perfOver(chart.bars, 63),
        },
        source: "yfinance",
      });
    }
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