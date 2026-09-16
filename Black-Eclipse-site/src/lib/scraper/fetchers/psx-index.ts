// ── PSX index fetcher — KSE-100 / KSE-30 / KMI-30 daily bars ────────────────
// Yahoo dropped PSX index coverage (^KSE100, KSE100.KA and .PSX all 404), so
// Pakistan's benchmarks need their own source. The exchange publishes them:
//
//   POST https://dps.psx.com.pk/historical  (symbol, month, year) → HTML table
//   GET  https://dps.psx.com.pk/timeseries/eod/<symbol>            → JSON, 5y
//
// The POST endpoint is the one with true OHLC. It returns ONE MONTH per call, so
// a multi-month series is fetched as a few parallel calls. Rows look like:
//
//   Sep 16, 2026 | 169,151.90 | 169,382.01 | 167,849.70 | 168,021.80 | 127,596,823
//   date         | open       | high       | low        | close      | volume
//
// (Verified field order by cross-checking OGDC against Yahoo's .KA series.)

import type { PriceBar as Bar } from '@/lib/chart/types';

const PSX_HISTORICAL = 'https://dps.psx.com.pk/historical';

// The endpoint serves an HTML fragment gated on a browser-ish UA + XHR header.
const HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
  Accept: 'text/html,application/xhtml+xml',
  'X-Requested-With': 'XMLHttpRequest',
};

/** Strip thousands separators, empty cells and stray tags from a PSX cell. */
function num(raw: string | undefined): number | null {
  if (!raw) return null;
  const cleaned = raw.replace(/<[^>]+>/g, '').replace(/[,\s]/g, '').trim();
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** "Sep 16, 2026" → "2026-09-16". Returns null when unparseable. */
function isoDate(raw: string | undefined): string | null {
  if (!raw) return null;
  const cleaned = raw.replace(/<[^>]+>/g, '').trim();
  const d = new Date(cleaned);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

/**
 * Parse one monthly `historical` HTML response into bars.
 * Exported for tests — the HTML shape is the fragile part.
 */
export function parsePsxHistorical(html: string): Bar[] {
  const bars: Bar[] = [];
  const rows = html.matchAll(/<tr>([\s\S]*?)<\/tr>/g);
  for (const row of rows) {
    const cells = [...row[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(m => m[1]);
    if (cells.length < 6) continue; // header / spacer row
    const date = isoDate(cells[0]);
    const open = num(cells[1]);
    const high = num(cells[2]);
    const low = num(cells[3]);
    const close = num(cells[4]);
    const volume = num(cells[5]);
    if (!date || close == null || close <= 0) continue;
    bars.push({
      date,
      time: Date.parse(`${date}T00:00:00Z`),
      open: open ?? close,
      high: high ?? close,
      low: low ?? close,
      close,
      volume,
    });
  }
  return bars;
}

async function fetchMonth(symbol: string, month: number, year: number): Promise<Bar[]> {
  try {
    const res = await fetch(PSX_HISTORICAL, {
      method: 'POST',
      headers: { ...HEADERS, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `symbol=${encodeURIComponent(symbol)}&month=${month}&year=${year}`,
      signal: AbortSignal.timeout(20000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    return parsePsxHistorical(await res.text());
  } catch {
    return [];
  }
}

/** The symbol the PSX endpoint expects: the canonical one without the caret. */
export function psxTicker(symbol: string): string {
  return symbol.trim().toUpperCase().replace(/^\^/, '');
}

// ── Latest quote (chart footer / live price line) ────────────────────────────
// The `eod` endpoint returns ~5 years of daily rows in one call, newest first:
//   [epochSeconds, close, volume, open]
// Only the newest row is needed, so the result is cached briefly.

const PSX_EOD = 'https://dps.psx.com.pk/timeseries/eod';

export interface PsxQuote {
  symbol: string;
  price: number;
  /** Percent change vs the previous session's close. */
  changePct: number;
  previousClose: number;
  volume: number | null;
  /** Trading date of the quote (YYYY-MM-DD). */
  date: string;
}

/**
 * Parse the `eod` JSON payload. Exported for tests.
 * `data[0]` is the latest session; `data[1]` the previous one.
 */
export function parsePsxEod(json: unknown, symbol: string): PsxQuote | null {
  const rows = (json as { data?: unknown[] } | null)?.data;
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const latest = rows[0] as unknown[];
  const prev = rows[1] as unknown[] | undefined;
  const price = Number(latest?.[1]);
  if (!Number.isFinite(price) || price <= 0) return null;
  const previousClose = prev ? Number(prev[1]) : NaN;
  const changePct =
    Number.isFinite(previousClose) && previousClose > 0
      ? ((price - previousClose) / previousClose) * 100
      : 0;
  const ts = Number(latest[0]);
  return {
    symbol,
    price,
    previousClose: Number.isFinite(previousClose) ? previousClose : price,
    changePct,
    volume: Number.isFinite(Number(latest[2])) ? Number(latest[2]) : null,
    date: Number.isFinite(ts)
      ? new Date(ts * 1000).toISOString().slice(0, 10)
      : new Date().toISOString().slice(0, 10),
  };
}

const quoteCache = new Map<string, { t: number; quote: PsxQuote | null }>();
const QUOTE_TTL_MS = 5 * 60 * 1000;

/** Latest real quote for a PSX index, or null when unavailable. */
export async function fetchPsxIndexQuote(symbol: string): Promise<PsxQuote | null> {
  const ticker = psxTicker(symbol);
  if (!ticker) return null;
  const cached = quoteCache.get(ticker);
  if (cached && Date.now() - cached.t < QUOTE_TTL_MS) return cached.quote;

  let quote: PsxQuote | null = null;
  try {
    const res = await fetch(`${PSX_EOD}/${encodeURIComponent(ticker)}`, {
      headers: HEADERS,
      signal: AbortSignal.timeout(15000),
      cache: 'no-store',
    });
    if (res.ok) quote = parsePsxEod(await res.json(), ticker);
  } catch {
    quote = null;
  }
  quoteCache.set(ticker, { t: Date.now(), quote });
  return quote;
}

/** How many calendar months of history to request. */
const MONTHS = 6;

/**
 * Fetch a daily OHLCV series for a PSX index. One request per month, issued in
 * parallel (measured ~1.6s for six months), de-duplicated by date and sorted
 * oldest-first. Returns [] when the index has no published data.
 */
export async function fetchPsxIndexChart(symbol: string): Promise<Bar[]> {
  const ticker = psxTicker(symbol);
  if (!ticker) return [];

  const now = new Date();
  const requests: Array<Promise<Bar[]>> = [];
  for (let i = 0; i < MONTHS; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    requests.push(fetchMonth(ticker, d.getMonth() + 1, d.getFullYear()));
  }
  const months = await Promise.all(requests);

  const byDate = new Map<string, Bar>();
  for (const bars of months) {
    for (const bar of bars) byDate.set(bar.date, bar);
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}
