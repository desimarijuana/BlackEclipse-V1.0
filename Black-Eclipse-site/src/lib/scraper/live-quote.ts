// ── On-demand live quotes (read-through) ─────────────────────────────────────
// The background scraper writes the JDDS `Price` row on a 15-minute cycle, so
// serving `/api/quote` from the DB alone made every 30-second poll return the
// same up-to-15-minute-old number — the chart, header ribbon and portfolio
// looked badly delayed even though they polled frequently.
//
// This module adds a short-lived read-through: when the stored row is older
// than `LIVE_QUOTE_TTL_MS`, fetch the live quote directly from Yahoo's chart
// endpoint (one cheap browser-UA HTTP request — no Python spawn) and return
// that. A small in-memory cache with in-flight dedup means N clients share ONE
// upstream call per symbol per TTL window, so the poll cadence never fans out
// into a request storm. It NEVER fabricates: a failed fetch returns null and the
// caller keeps the (honestly-labelled) stored value.

import { fetchYahooChartSeries, yahooChartCandidates } from './yahoo-chart';
import { resolveIndex } from '@/lib/indices';

export interface LiveQuote {
  symbol: string;
  market: string;
  price: number;
  previousClose: number | null;
  changePct: number | null;
  currency: string | null;
  /** Epoch ms the live value was observed. */
  at: number;
}

/** How long a live value is shared before another upstream fetch is allowed. */
export const LIVE_QUOTE_TTL_MS = 15_000;
/** A stored row younger than this is trusted as-is (no read-through). */
export const STORED_QUOTE_FRESH_MS = 60_000;

interface CacheEntry {
  quote: LiveQuote | null;
  at: number;
}

const cache = new Map<string, CacheEntry>();
const inFlight = new Map<string, Promise<LiveQuote | null>>();

function keyFor(symbol: string, market: string): string {
  return `${symbol.toUpperCase()}|${market.toUpperCase()}`;
}

async function fetchOne(symbol: string, market: string): Promise<LiveQuote | null> {
  // PSX indices have no Yahoo instrument — the caller uses the exchange endpoint.
  const def = resolveIndex(symbol);
  if (def?.provider === 'psx') return null;

  for (const ticker of yahooChartCandidates(symbol, market)) {
    // 5d/5m guarantees enough bars for any trading instrument while `meta`
    // (regularMarketPrice) stays the live price regardless of range.
    const chart = await fetchYahooChartSeries(ticker, '5d', '5m');
    if (chart && chart.meta.price && chart.meta.price > 0) {
      return {
        symbol: symbol.toUpperCase(),
        market: market.toUpperCase(),
        price: chart.meta.price,
        previousClose: chart.meta.previousClose,
        changePct: chart.meta.changePct,
        currency: chart.meta.currency,
        at: Date.now(),
      };
    }
  }
  return null;
}

/**
 * Get the live quote for one symbol, using the shared cache + dedup. Returns
 * null when Yahoo has no price (caller falls back to the stored row honestly).
 */
export async function getLiveQuote(symbol: string, market: string): Promise<LiveQuote | null> {
  const key = keyFor(symbol, market);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < LIVE_QUOTE_TTL_MS) return hit.quote;

  const existing = inFlight.get(key);
  if (existing) return existing;

  const task = (async () => {
    try {
      const quote = await fetchOne(symbol, market);
      // Cache a negative result too (short TTL) so a dead symbol does not hammer
      // upstream on every poll.
      cache.set(key, { quote, at: Date.now() });
      return quote;
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, task);
  return task;
}

/** Fetch many quotes concurrently, capped. Returns a map keyed by UPPERCASE symbol. */
export async function getLiveQuotes(
  requests: Array<{ symbol: string; market: string }>,
  concurrency = 6,
): Promise<Map<string, LiveQuote>> {
  const out = new Map<string, LiveQuote>();
  const queue = [...requests];
  async function worker() {
    while (queue.length > 0) {
      const next = queue.shift();
      if (!next) break;
      const q = await getLiveQuote(next.symbol, next.market);
      if (q) out.set(next.symbol.toUpperCase(), q);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, worker));
  return out;
}

/** Clear the cache (tests / manual refresh). */
export function clearLiveQuoteCache(): void {
  cache.clear();
}
