// ── Yahoo chart fetch (direct HTTP, no Python) ───────────────────────────────
// The v8 chart endpoint is one cheap browser-UA HTTP request and works for
// stocks, ETFs, crypto, futures and indices. It backs the on-demand live-quote
// read-through (see `live-quote.ts`) and the price-history route. Deliberately
// NOT the yfinance bridge: that spawns a Python process per call, which is fine
// for scheduled batches but far too slow to run on a 30-second poll.

import { resolveIndex } from '@/lib/indices';
import { stripExchangeSuffix } from '@/lib/utils';
import { yahooSymbol } from './fetchers/yfinance';

export interface Bar {
  date: string;
  time?: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export interface ChartMeta {
  price: number | null;
  previousClose: number | null;
  changePct: number | null;
  currency: string | null;
}

const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

/**
 * Candidate Yahoo tickers to try, in order, for one symbol+market.
 *
 * Index aliases resolve FIRST: a bare TradingView-style id (`SPX`, `DJI`,
 * `NIFTY`) has no Yahoo instrument, so it is mapped to its real ticker
 * (`^GSPC`, `^DJI`, `^NSEI`). PSX indices are excluded — Yahoo dropped them.
 */
export function yahooChartCandidates(symbol: string, market: string): string[] {
  const idx = resolveIndex(symbol);
  const candidates: string[] = [];
  if (idx && idx.provider === 'yahoo') {
    candidates.push(idx.symbol);
    if (!candidates.includes(symbol)) candidates.push(symbol);
    return candidates;
  }

  candidates.push(yahooSymbol(symbol, market));
  if (market === 'PK') {
    // Yahoo serves PSX under the KAR exchange (.KA); the .PSX suffix 404s.
    const bare = symbol.replace(/\.PSX$/i, '');
    if (!candidates.includes(`${bare}.KA`)) candidates.push(`${bare}.KA`);
    if (!candidates.includes(bare)) candidates.push(bare);
  }
  const bare = stripExchangeSuffix(symbol);
  if (bare !== symbol.toUpperCase() && !candidates.includes(bare)) candidates.push(bare);
  return candidates;
}

interface YahooChartJson {
  chart?: {
    result?: Array<{
      meta?: {
        regularMarketPrice?: number;
        previousClose?: number;
        chartPreviousClose?: number;
        currency?: string;
      };
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          open?: (number | null)[];
          high?: (number | null)[];
          low?: (number | null)[];
          close?: (number | null)[];
          volume?: (number | null)[];
        }>;
      };
    }>;
  };
}

/**
 * Fetch one Yahoo chart for one ticker. Returns the parsed bars and the
 * `meta` block (which carries the live regular-market price + previous close,
 * so a real-time quote never has to be reconstructed from a possibly-stale bar).
 */
export async function fetchYahooChartSeries(
  ticker: string,
  range: string,
  interval = '1d',
): Promise<{ bars: Bar[]; meta: ChartMeta } | null> {
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}` +
    `?range=${range}&interval=${interval}&includePrePost=false`;
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': BROWSER_UA, Accept: 'application/json' },
      signal: AbortSignal.timeout(20000),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const json = (await res.json()) as YahooChartJson;
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
    if (bars.length < 2) return null;

    const m = result?.meta;
    const lastClose = bars[bars.length - 1].close;
    const price = typeof m?.regularMarketPrice === 'number' && m.regularMarketPrice > 0
      ? m.regularMarketPrice
      : lastClose;
    const previousClose =
      typeof m?.previousClose === 'number' && m.previousClose > 0
        ? m.previousClose
        : typeof m?.chartPreviousClose === 'number' && m.chartPreviousClose > 0
          ? m.chartPreviousClose
          : null;
    const changePct = previousClose && previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : null;
    return {
      bars,
      meta: { price, previousClose, changePct, currency: m?.currency ?? null },
    };
  } catch {
    return null;
  }
}
