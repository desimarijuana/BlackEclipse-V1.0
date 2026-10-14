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
  /** Yahoo-provided identity fields (used for on-demand resolution). */
  longName: string | null;
  shortName: string | null;
  exchange: string | null;
  instrumentType: string | null;
}

/** Inclusive epoch-ms bounds for a requested window (bare dates pad to end-of-day). */
export interface WindowBounds {
  startMs: number | null;
  endMs: number | null;
}

/** Parse a window from `start`/`end` strings (`YYYY-MM-DD` or a full timestamp). */
export function windowBounds(start?: string, end?: string): WindowBounds {
  const parse = (value: string | undefined, endOfDay: boolean): number | null => {
    if (!value) return null;
    const text = value.trim();
    if (!text) return null;
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text);
    const ms = Date.parse(dateOnly ? `${text}T00:00:00Z` : text);
    if (!Number.isFinite(ms)) return null;
    return ms + (endOfDay && dateOnly ? 86_399_000 : 0);
  };
  return { startMs: parse(start, false), endMs: parse(end, true) };
}

/** True when a bar timestamp (ISO date, epoch seconds or epoch ms) is inside the window. */
export function timestampWithinWindow(ts: string, bounds: WindowBounds): boolean {
  if (bounds.startMs == null && bounds.endMs == null) return true;
  if (!ts) return true;
  const numeric = Number(ts);
  const ms = /^\d{4}-\d{2}-\d{2}/.test(ts)
    ? Date.parse(ts)
    : Number.isFinite(numeric)
      ? numeric < 1e12
        ? numeric * 1000
        : numeric
      : NaN;
  if (!Number.isFinite(ms)) return true; // an unparsable stamp is kept, never dropped
  if (bounds.startMs != null && ms < bounds.startMs) return false;
  if (bounds.endMs != null && ms > bounds.endMs) return false;
  return true;
}

// The smallest Yahoo `range` that COVERS a requested span, so a start date no
// longer collapses to "max" (the full history) for every window.
const RANGE_SPAN_DAYS: Array<[string, number]> = [
  ['1d', 1], ['5d', 5], ['1mo', 31], ['3mo', 92], ['6mo', 183],
  ['1y', 366], ['2y', 731], ['5y', 1827], ['10y', 3652], ['max', Number.POSITIVE_INFINITY],
];

/** The smallest range covering [startMs, endMs]; `fallback` when no start is given. */
export function coveringRangeFor(startMs: number | null, endMs: number | null, fallback: string): string {
  if (startMs == null) return fallback;
  const end = endMs ?? Date.now();
  const days = Math.max(1, Math.ceil((end - startMs) / 86_400_000));
  return RANGE_SPAN_DAYS.find(([, span]) => days <= span)?.[0] ?? 'max';
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
  // Per-market fallback chains for thin markets whose primary Yahoo suffix 404s
  // or is unreliable. Each entry is tried in order (Harness closeout Phase 4.5).
  // PK: Yahoo serves PSX under the KAR exchange (.KA); the .PSX suffix 404s.
  const fallbacks: Record<string, string[]> = {
    PK: ['.KA'],
    // Thin venues: try the bare local code and a common alternative suffix.
    VN: ['', '.HM'],
    TH: ['', '.BK'],
    MX: ['', '.MX'],
    NG: ['', '.LG'],
    EG: ['', '.CA'],
    ID: ['', '.JK'],
    ZA: ['', '.JO'],
  };
  const bare = stripExchangeSuffix(symbol);
  for (const suffix of fallbacks[market] ?? []) {
    const candidate = suffix ? `${bare}${suffix}` : bare;
    if (!candidates.includes(candidate)) candidates.push(candidate);
  }
  if (bare !== symbol.toUpperCase() && !candidates.includes(bare)) candidates.push(bare);
  return candidates;
}

/**
 * Choose the quote price from Yahoo's `meta.regularMarketPrice` and the newest
 * real bar close. Yahoo's meta price is occasionally stale/bogus (observed:
 * `OGDC.KA` meta 131.87 while the real latest close was 315.91). We therefore
 * trust the meta price ONLY when it agrees with the newest actual bar within
 * `tolerance`; otherwise the bar is authoritative. This never invents a value —
 * both inputs are real, the guard just refuses an implausible one. A null/absent
 * meta price also falls back to the bar.
 */
export function selectChartPrice(
  metaPrice: number | null | undefined,
  lastClose: number,
  tolerance = 0.05,
): number {
  if (metaPrice == null || !Number.isFinite(metaPrice) || metaPrice <= 0) return lastClose;
  if (lastClose > 0 && Math.abs(metaPrice / lastClose - 1) > tolerance) return lastClose;
  return metaPrice;
}

interface YahooChartJson {
  chart?: {
    result?: Array<{
      meta?: {
        regularMarketPrice?: number;
        previousClose?: number;
        chartPreviousClose?: number;
        currency?: string;
        longName?: string;
        shortName?: string;
        exchangeName?: string;
        fullExchangeName?: string;
        instrumentType?: string;
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
  window?: { start?: string; end?: string },
): Promise<{ bars: Bar[]; meta: ChartMeta } | null> {
  // An explicit window is sent as `period1`/`period2` (epoch seconds): Yahoo
  // honours those EXACTLY, where `range` can only name a fixed preset. Without
  // this, a Dec-2025 window returned the entire history and downstream code
  // truncated head+tail.
  const bounds = windowBounds(window?.start, window?.end);
  const span =
    bounds.startMs != null
      ? `&period1=${Math.floor(bounds.startMs / 1000)}` +
        (bounds.endMs != null ? `&period2=${Math.floor(bounds.endMs / 1000)}` : '')
      : `&range=${range}`;
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}` +
    `?interval=${interval}&includePrePost=false${span}`;
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
    // Guard against a stale/bogus regularMarketPrice (see selectChartPrice).
    const price = selectChartPrice(
      typeof m?.regularMarketPrice === 'number' ? m.regularMarketPrice : null,
      lastClose,
    );
    const previousClose =
      typeof m?.previousClose === 'number' && m.previousClose > 0
        ? m.previousClose
        : typeof m?.chartPreviousClose === 'number' && m.chartPreviousClose > 0
          ? m.chartPreviousClose
          : null;
    const changePct = previousClose && previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : null;
    return {
      bars,
      meta: {
        price,
        previousClose,
        changePct,
        currency: m?.currency ?? null,
        longName: typeof m?.longName === 'string' ? m.longName : null,
        shortName: typeof m?.shortName === 'string' ? m.shortName : null,
        exchange: (typeof m?.fullExchangeName === 'string' && m.fullExchangeName) || (typeof m?.exchangeName === 'string' ? m.exchangeName : null) || null,
        instrumentType: typeof m?.instrumentType === 'string' ? m.instrumentType : null,
      },
    };
  } catch {
    return null;
  }
}
