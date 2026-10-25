import { describe, expect, it, vi } from 'vitest';
import {
  loadInteractiveDataset,
  normalizeHistoryPayload,
  validateDatasetRequest,
} from './dataset';

const request = { kind: 'series' as const, symbol: 'AAPL', range: '6mo' as const, interval: '1d' as const };

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    json: async () => payload,
  } as Response;
}

describe('interactive dataset bridge', () => {
  it('normalizes a real history payload', () => {
    const envelope = normalizeHistoryPayload(
      {
        series: [
          { date: '2026-10-23', open: 100, high: 105, low: 99, close: 104, volume: 1000 },
          { date: '2026-10-24', open: '104', high: '108', low: '103', close: '107', volume: null },
        ],
        source: 'yfinance',
        observationTime: '2026-10-24T20:00:00.000Z',
        freshness: 'live',
        stale: false,
        interval: '1d',
        currency: '$',
      },
      request,
    );
    expect(envelope.status).toBe('ready');
    if (envelope.status !== 'ready') return;
    expect(envelope.bars).toHaveLength(2);
    expect(envelope.bars[1]).toMatchObject({ open: 104, close: 107 });
    expect(envelope.asOf).toBe('2026-10-24');
    expect(envelope.source).toBe('yfinance');
    expect(envelope.stale).toBe(false);
  });

  it('reports an honest unavailable state when the series is empty', () => {
    const envelope = normalizeHistoryPayload({ series: [], source: 'none' }, request);
    expect(envelope).toEqual({ status: 'unavailable', reason: 'No price series for AAPL.' });
  });

  it('drops malformed rows instead of inventing values', () => {
    const envelope = normalizeHistoryPayload(
      { series: [{ date: '2026-10-24', open: null, close: 10 }, { date: 'x', close: 1 }], source: 'yfinance' },
      request,
    );
    expect(envelope.status).toBe('unavailable');
  });

  it('rejects invalid requests before fetching', async () => {
    expect(validateDatasetRequest({ ...request, symbol: '<script>' })).toBe('Invalid symbol.');
    const fetchImpl = vi.fn();
    const envelope = await loadInteractiveDataset(
      { ...request, symbol: '<script>' },
      { fetchImpl: fetchImpl as unknown as typeof fetch },
    );
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(envelope.status).toBe('unavailable');
  });

  it('fetches through the existing price-history route', async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) =>
      jsonResponse({ series: [{ date: '2026-10-24', open: 1, high: 2, low: 1, close: 2 }], source: 'yfinance' }),
    );
    const envelope = await loadInteractiveDataset(request, {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(String(fetchImpl.mock.calls[0][0])).toContain('/api/price-history?symbol=AAPL');
    expect(envelope.status).toBe('ready');
  });

  it('surfaces an HTTP failure as unavailable', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, false));
    const envelope = await loadInteractiveDataset(request, {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(envelope.status).toBe('unavailable');
  });

  it('surfaces a network failure as unavailable', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('offline');
    });
    const envelope = await loadInteractiveDataset(request, {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(envelope).toEqual({ status: 'unavailable', reason: 'Could not load market data.' });
  });
});
