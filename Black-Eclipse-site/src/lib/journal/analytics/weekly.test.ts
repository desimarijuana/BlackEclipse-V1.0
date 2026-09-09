import { describe, it, expect } from 'vitest';
import { buildWeeklyReview, buildRecentWeeklyReviews, filterByRange } from './weekly';
import { buildMonthlyWrapped } from './wrapped';
import { byHour, byTimeframe } from './dimensions';
import { confidenceCorrelation } from './psychology';
import type { TradeRecord } from './types';

function trade(overrides: Partial<TradeRecord>): TradeRecord {
  return {
    id: 't1', symbol: 'XAUUSD', direction: 'LONG', entry: 100, exit: 110,
    stopLoss: 99, takeProfit: 120, quantity: 1,
    entryTime: '2026-09-01T09:30:00.000Z', exitTime: '2026-09-01T10:00:00.000Z',
    status: 'closed', pnl: 10, pnlPct: 0.1, rMultiple: 2, riskAmount: 1,
    rewardAmount: 21, actualRR: 2.1, durationSec: 1800, mfe: null, mae: null,
    emotion: 'Calm', confidence: 4, session: 'New York', timeframe: '15m', marketRegime: 'Trending',
    ...overrides,
  };
}

describe('byHour', () => {
  it('groups trades by UTC hour', () => {
    const trades = [
      trade({ id: 'a', rMultiple: 2, exitTime: '2026-09-01T10:00:00.000Z' }),
      trade({ id: 'b', rMultiple: -1, exitTime: '2026-09-02T10:30:00.000Z' }),
      trade({ id: 'c', rMultiple: 3, exitTime: '2026-09-03T14:00:00.000Z' }),
    ];
    const rows = byHour(trades);
    expect(rows[0].key).toBe('14:00');
    expect(rows[0].netR).toBe(3);
    expect(rows[1].key).toBe('10:00');
    expect(rows[1].netR).toBe(1);
  });
});

describe('byTimeframe', () => {
  it('groups by timeframe', () => {
    const trades = [trade({ id: 'a', timeframe: '15m' }), trade({ id: 'b', timeframe: '1h' })];
    const rows = byTimeframe(trades);
    expect(rows.length).toBe(2);
  });
});

describe('confidenceCorrelation', () => {
  it('returns null with too few trades', () => {
    expect(confidenceCorrelation([trade({ id: 'a', confidence: 4 }), trade({ id: 'b', confidence: 3 })])).toBeNull();
  });

  it('returns a correlation with enough trades', () => {
    const trades = [
      trade({ id: 'a', confidence: 4, rMultiple: 2 }),
      trade({ id: 'b', confidence: 3, rMultiple: 1 }),
      trade({ id: 'c', confidence: 2, rMultiple: -1 }),
      trade({ id: 'd', confidence: 1, rMultiple: -2 }),
    ];
    const corr = confidenceCorrelation(trades);
    expect(corr).toBeGreaterThan(0.9);
  });
});

describe('filterByRange', () => {
  it('filters trades to inclusive range', () => {
    const trades = [
      trade({ id: 'a', exitTime: '2026-09-01T10:00:00.000Z' }),
      trade({ id: 'b', exitTime: '2026-09-05T10:00:00.000Z' }),
      trade({ id: 'c', exitTime: '2026-09-10T10:00:00.000Z' }),
    ];
    const result = filterByRange(trades, '2026-09-02', '2026-09-08');
    expect(result.length).toBe(1);
    expect(result[0].id).toBe('b');
  });
});

describe('buildWeeklyReview', () => {
  it('produces a structured weekly review', () => {
    const trades = [
      trade({ id: 'a', symbol: 'XAUUSD', setupName: 'BOS + FVG', rMultiple: 2, exitTime: '2026-09-01T10:00:00.000Z' }),
      trade({ id: 'b', symbol: 'NQ', setupName: 'Breakout', rMultiple: -1, exitTime: '2026-09-02T10:00:00.000Z' }),
    ];
    const review = buildWeeklyReview(trades, '2026-09-01', '2026-09-07');
    expect(review.performance.trades).toBe(2);
    expect(review.performance.netR).toBe(1);
    expect(review.sections.length).toBeGreaterThan(0);
  });
});

describe('buildRecentWeeklyReviews', () => {
  it('builds 4 weekly reviews', () => {
    const reviews = buildRecentWeeklyReviews([], 4);
    expect(reviews.length).toBe(4);
  });
});

describe('buildMonthlyWrapped', () => {
  it('produces a wrapped report for the current month', () => {
    const trades = [
      trade({ id: 'a', symbol: 'XAUUSD', setupName: 'BOS + FVG', session: 'New York', rMultiple: 2 }),
      trade({ id: 'b', symbol: 'NQ', setupName: 'Breakout', session: 'London', rMultiple: -1 }),
    ];
    const now = new Date();
    const wrapped = buildMonthlyWrapped(trades, now.getUTCFullYear(), now.getUTCMonth());
    expect(wrapped.performance.trades).toBe(2);
    expect(wrapped.bestMarket?.key).toBe('XAUUSD');
  });
});
