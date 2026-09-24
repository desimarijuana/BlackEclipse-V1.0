// ── DataSubscriptionManager tests ─────────────────────────────────────────────
// The whole point of the manager is spec §9: duplicate charts of the same
// instrument must NOT create duplicate upstream subscriptions. These tests mock
// fetch and assert the dedup contract directly.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { DataSubscriptionManager, barsTtl, barsRefreshMs } from './subscription-manager';
import { DAILY_HISTORY_TTL_MS } from './price-history-ttl';

const originalFetch = global.fetch;

function mockFetch(handler: (url: string) => { ok?: boolean; json: unknown }) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const res = handler(url);
    return {
      ok: res.ok ?? true,
      json: async () => res.json,
    } as Response;
  }) as unknown as typeof fetch;
}

describe('DataSubscriptionManager — bars', () => {
  beforeEach(() => { global.fetch = originalFetch; });
  afterEach(() => { global.fetch = originalFetch; vi.restoreAllMocks(); });

  it('shares ONE request across duplicate symbol subscriptions', async () => {
    const fetches: string[] = [];
    mockFetch((url) => {
      fetches.push(url);
      return { json: { symbol: 'AAPL', currency: '$', source: 'yfinance', series: [
        { date: '2025-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 },
        { date: '2025-01-02', open: 1.5, high: 2, low: 1, close: 1.8, volume: 120 },
      ] } };
    });

    const mgr = new DataSubscriptionManager();
    const seen: unknown[] = [];
    const unsubA = mgr.subscribeBars('AAPL', 'US', '1D', (e) => seen.push(e.data));
    const unsubB = mgr.subscribeBars('AAPL', 'US', '1D', (e) => seen.push(e.data));
    const unsubC = mgr.subscribeBars('AAPL', 'US', '1D', (e) => seen.push(e.data));

    await vi.waitFor(() => expect(seen.some(Boolean)).toBe(true));
    // All three listeners resolved the same bars.
    expect(seen.filter(Boolean).length).toBeGreaterThanOrEqual(3);
    // Exactly one upstream request for the one identity.
    expect(fetches).toHaveLength(1);
    expect(fetches[0]).toContain('AAPL');
    expect(mgr.stats().bars).toBe(1);

    unsubA(); unsubB(); unsubC();
  });

  it('does a separate request per distinct identity', async () => {
    const fetches: string[] = [];
    mockFetch((url) => {
      fetches.push(url);
      return { json: { symbol: 'X', currency: '$', source: 'yfinance', series: [
        { date: '2025-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 },
        { date: '2025-01-02', open: 1.5, high: 2, low: 1, close: 1.8, volume: 1 },
      ] } };
    });
    const mgr = new DataSubscriptionManager();
    const u1 = mgr.subscribeBars('AAPL', 'US', '1D', () => {});
    const u2 = mgr.subscribeBars('AAPL', 'US', '1H', () => {});
    await vi.waitFor(() => expect(fetches.length).toBe(2));
    expect(mgr.stats().bars).toBe(2);
    u1(); u2();
  });

  it('serves cached data after all listeners leave and re-subscribe', async () => {
    const fetches: string[] = [];
    mockFetch((url) => {
      fetches.push(url);
      return { json: { symbol: 'AAPL', currency: '$', source: 'yfinance', series: [
        { date: '2025-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 },
        { date: '2025-01-02', open: 1.5, high: 2, low: 1, close: 1.8, volume: 1 },
      ] } };
    });
    const mgr = new DataSubscriptionManager();
    let dataLoaded = false;
    const u1 = mgr.subscribeBars('AAPL', 'US', '1D', (e) => { if (e.data) dataLoaded = true; });
    await vi.waitFor(() => expect(dataLoaded).toBe(true));
    expect(fetches).toHaveLength(1);
    u1();
    // Re-subscribe — must reuse the cache, not re-hit upstream.
    const got: unknown[] = [];
    const u2 = mgr.subscribeBars('AAPL', 'US', '1D', (e) => got.push(e.data));
    expect(got.some(Boolean)).toBe(true);
    expect(fetches).toHaveLength(1);
    u2();
  });
});

describe('barsTtl / barsRefreshMs (timeframe-aware freshness)', () => {
  it('gives intraday timeframes a short TTL and daily a long one', () => {
    expect(barsTtl('1m')).toBe(30_000);
    expect(barsTtl('5m')).toBe(60_000);
    expect(barsTtl('15m')).toBeLessThan(DAILY_HISTORY_TTL_MS);
    expect(barsTtl('1H')).toBeLessThan(DAILY_HISTORY_TTL_MS);
    expect(barsTtl('1D')).toBe(DAILY_HISTORY_TTL_MS);
    expect(barsTtl('1W')).toBe(DAILY_HISTORY_TTL_MS);
  });

  it('auto-refreshes intraday series but leaves daily on demand only', () => {
    expect(barsRefreshMs('1m')).toBeGreaterThan(0);
    expect(barsRefreshMs('5m')).toBeGreaterThan(0);
    expect(barsRefreshMs('1H')).toBeGreaterThan(0);
    // Daily+ never polls — the long TTL plus the on-demand refresh covers them.
    expect(barsRefreshMs('1D')).toBe(0);
    expect(barsRefreshMs('1W')).toBe(0);
    expect(barsRefreshMs('1M')).toBe(0);
  });
});

describe('DataSubscriptionManager — intraday auto-refresh', () => {
  beforeEach(() => {
    global.fetch = originalFetch;
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('re-fetches an intraday series on the refresh cadence', async () => {
    const fetches: string[] = [];
    mockFetch((url) => {
      fetches.push(url);
      return { json: { symbol: 'AAPL', currency: '$', source: 'yfinance', series: [
        { date: '2025-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 },
        { date: '2025-01-02', open: 1.5, high: 2, low: 1, close: 1.8, volume: 1 },
      ] } };
    });
    const mgr = new DataSubscriptionManager();
    const unsub = mgr.subscribeBars('AAPL', 'US', '1m', () => {});
    await vi.waitFor(() => expect(fetches.length).toBe(1));

    // Advance past one refresh interval; the series must refresh silently.
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetches.length).toBeGreaterThanOrEqual(2);
    unsub();
  });
});

describe('DataSubscriptionManager — batch quotes', () => {
  beforeEach(() => { global.fetch = originalFetch; });
  afterEach(() => { global.fetch = originalFetch; vi.restoreAllMocks(); });

  it('shares ONE batch request for the same symbol set', async () => {
    const fetches: string[] = [];
    mockFetch((url) => {
      fetches.push(url);
      return { json: { quotes: [{ symbol: 'AAPL', name: 'Apple', price: 100, changePercent: 1, currency: '$', found: true }] } };
    });
    const mgr = new DataSubscriptionManager();
    const u1 = mgr.subscribeBatch(['AAPL', 'MSFT'], () => {});
    const u2 = mgr.subscribeBatch(['MSFT', 'AAPL'], () => {}); // same set, different order
    await vi.waitFor(() => expect(fetches.length).toBeGreaterThanOrEqual(1));
    expect(fetches).toHaveLength(1);
    expect(mgr.stats().batches).toBe(1);
    u1(); u2();
  });
});
