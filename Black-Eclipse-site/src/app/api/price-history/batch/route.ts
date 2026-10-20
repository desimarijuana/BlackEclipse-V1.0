import { NextResponse } from 'next/server';
import { GET as getHistory } from '../route';

export const dynamic = 'force-dynamic';

/**
 * Batched price history for a portfolio/watchlist.
 *
 * The per-symbol route stays the source of truth (caching, market discovery,
 * snapshot fallback), but a portfolio used to issue one request per holding —
 * the browser caps a host at ~6 concurrent connections, so the tail serialized.
 * This fans the same work out server-side and returns one map.
 *
 * Request:  { symbols: [{ symbol, market? }], range?, interval? }
 * Response: { seriesBySymbol: { [symbol]: <the per-symbol payload> } }
 */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    symbols?: unknown;
    range?: unknown;
    interval?: unknown;
  };
  const items = Array.isArray(body.symbols) ? body.symbols.slice(0, 100) : [];
  const range = typeof body.range === 'string' && body.range ? body.range : '3mo';
  const interval = typeof body.interval === 'string' && body.interval ? body.interval : '1d';

  const entries = await Promise.all(
    items.map(async (raw) => {
      const item = raw as { symbol?: unknown; market?: unknown };
      const symbol = typeof item?.symbol === 'string' ? item.symbol.trim().toUpperCase() : '';
      if (!symbol) return null;
      const market = typeof item?.market === 'string' && item.market ? item.market.trim().toUpperCase() : 'US';

      const url = new URL('/api/price-history', request.url);
      url.searchParams.set('symbol', symbol);
      url.searchParams.set('market', market);
      url.searchParams.set('range', range);
      url.searchParams.set('interval', interval);

      const response = await getHistory(new Request(url.toString()));
      const payload = await response.json().catch(() => ({}));
      return [symbol, payload] as const;
    }),
  );

  const seriesBySymbol = Object.fromEntries(
    entries.filter((entry): entry is readonly [string, unknown] => entry !== null),
  );
  return NextResponse.json({ seriesBySymbol });
}
