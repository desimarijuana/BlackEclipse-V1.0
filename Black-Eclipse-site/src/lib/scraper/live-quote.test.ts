import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getLiveQuote, getLiveQuotes, clearLiveQuoteCache, LIVE_QUOTE_TTL_MS } from './live-quote';

const originalFetch = global.fetch;

function chartResponse(price: number, prevClose = price) {
  const nowSec = Math.floor(Date.now() / 1000);
  return {
    chart: {
      result: [
        {
          meta: { regularMarketPrice: price, previousClose: prevClose, currency: 'USD' },
          timestamp: [nowSec - 120, nowSec - 60, nowSec],
          indicators: {
            quote: [{ open: [1, 1, 1], high: [1, 1, 1], low: [1, 1, 1], close: [prevClose, prevClose, price], volume: [1, 1, 1] }],
          },
        },
      ],
    },
  };
}

function mockChart(handler: (url: string) => unknown | null) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = handler(url);
    if (body === null) return { ok: false, json: async () => ({}) } as Response;
    return { ok: true, json: async () => body } as Response;
  }) as unknown as typeof fetch;
}

describe('live-quote read-through', () => {
  beforeEach(() => {
    global.fetch = originalFetch;
    clearLiveQuoteCache();
  });
  afterEach(() => {
    global.fetch = originalFetch;
    clearLiveQuoteCache();
    vi.restoreAllMocks();
  });

  it('fetches the live price from Yahoo and reports the change', async () => {
    mockChart(() => chartResponse(105, 100));
    const q = await getLiveQuote('AAPL', 'US');
    expect(q).not.toBeNull();
    expect(q!.price).toBe(105);
    expect(q!.changePct).toBeCloseTo(5, 5);
    expect(q!.currency).toBe('USD');
  });

  it('serves from cache within the TTL (one upstream call)', async () => {
    const fetches: string[] = [];
    mockChart((url) => { fetches.push(url); return chartResponse(100, 100); });
    await getLiveQuote('AAPL', 'US');
    await getLiveQuote('AAPL', 'US');
    await getLiveQuote('AAPL', 'US');
    expect(fetches).toHaveLength(1);
  });

  it('dedupes concurrent requests for the same symbol', async () => {
    const fetches: string[] = [];
    mockChart((url) => { fetches.push(url); return chartResponse(100, 100); });
    const results = await Promise.all([
      getLiveQuote('AAPL', 'US'),
      getLiveQuote('AAPL', 'US'),
      getLiveQuote('AAPL', 'US'),
    ]);
    expect(fetches).toHaveLength(1);
    expect(results.every((r) => r?.price === 100)).toBe(true);
  });

  it('returns null (no fabrication) when Yahoo has nothing', async () => {
    mockChart(() => null);
    expect(await getLiveQuote('DEAD', 'US')).toBeNull();
  });

  it('caches a negative result so a dead symbol does not hammer upstream', async () => {
    const fetches: string[] = [];
    mockChart((url) => { fetches.push(url); return null; });
    await getLiveQuote('DEAD', 'US');
    await getLiveQuote('DEAD', 'US');
    // Two candidate tickers attempted once, then served from the negative cache.
    expect(fetches.length).toBeLessThanOrEqual(2);
  });

  it('batch fetch maps results by uppercase symbol', async () => {
    mockChart(() => chartResponse(50, 50));
    const map = await getLiveQuotes([
      { symbol: 'aaa', market: 'US' },
      { symbol: 'BBB', market: 'US' },
    ]);
    expect(map.has('AAA')).toBe(true);
    expect(map.has('BBB')).toBe(true);
  });

  it('exposes a bounded positive TTL', () => {
    expect(LIVE_QUOTE_TTL_MS).toBeGreaterThan(0);
    expect(LIVE_QUOTE_TTL_MS).toBeLessThanOrEqual(60_000);
  });
});
