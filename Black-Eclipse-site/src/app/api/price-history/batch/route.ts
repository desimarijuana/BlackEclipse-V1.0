import { NextResponse } from 'next/server';
import { GET as getHistory } from '../route';

export const dynamic = 'force-dynamic';

/**
 * Batched price history for a portfolio/watchlist.
 *
 * The per-symbol route stays the source of truth (persisted-first cache, market
 * discovery, snapshot fallback). This endpoint fans the same work out
 * server-side with a BOUNDED pool: a portfolio of 40 holdings used to fire 40
 * concurrent upstream calls, which invites rate-limiting and makes the tail
 * slower than fetching them in order. Duplicate symbols are collapsed.
 *
 * Request:  { symbols: [{ symbol, market? }], range?, interval? }
 * Response: { seriesBySymbol: { [symbol]: <the per-symbol payload> } }
 */

const MAX_SYMBOLS = 100;
const MAX_CONCURRENCY = 8;
const PER_SYMBOL_TIMEOUT_MS = 12_000;

function unavailable(symbol: string, interval: string) {
  return {
    symbol,
    points: [],
    series: [],
    source: 'none',
    observationTime: null,
    retrievedAt: new Date().toISOString(),
    freshness: 'unavailable',
    stale: true,
    ageMs: null,
    interval,
  };
}

async function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((resolve) => {
        timer = setTimeout(() => resolve(fallback), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    symbols?: unknown;
    range?: unknown;
    interval?: unknown;
  };
  const range = typeof body.range === 'string' && body.range ? body.range : '3mo';
  const interval = typeof body.interval === 'string' && body.interval ? body.interval : '1d';

  // Collapse duplicates: two panels of AAPL must not become two requests.
  const seen = new Set<string>();
  const items: Array<{ symbol: string; market: string }> = [];
  if (Array.isArray(body.symbols)) {
    for (const raw of body.symbols.slice(0, MAX_SYMBOLS)) {
      const item = raw as { symbol?: unknown; market?: unknown };
      const symbol = typeof item?.symbol === 'string' ? item.symbol.trim().toUpperCase() : '';
      if (!symbol) continue;
      const market = typeof item?.market === 'string' && item.market ? item.market.trim().toUpperCase() : 'US';
      const key = `${symbol}|${market}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ symbol, market });
    }
  }

  const seriesBySymbol: Record<string, unknown> = {};
  let cursor = 0;

  const worker = async () => {
    while (cursor < items.length) {
      const item = items[cursor];
      cursor += 1;
      const url = new URL('/api/price-history', request.url);
      url.searchParams.set('symbol', item.symbol);
      url.searchParams.set('market', item.market);
      url.searchParams.set('range', range);
      url.searchParams.set('interval', interval);
      try {
        const response = await withTimeout(
          getHistory(new Request(url.toString())),
          PER_SYMBOL_TIMEOUT_MS,
          NextResponse.json(unavailable(item.symbol, interval)),
        );
        seriesBySymbol[item.symbol] = await response.json().catch(() => unavailable(item.symbol, interval));
      } catch {
        seriesBySymbol[item.symbol] = unavailable(item.symbol, interval);
      }
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(MAX_CONCURRENCY, items.length) }, () => worker()),
  );

  return NextResponse.json({ seriesBySymbol });
}
