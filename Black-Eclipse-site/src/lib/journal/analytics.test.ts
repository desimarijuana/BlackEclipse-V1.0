import { describe, it, expect } from 'vitest';
import { computeTradeMath } from './trade-math';
import { computePerformance } from './analytics/performance';
import { computeDiscipline } from './analytics/discipline';
import { aggregateDays } from './analytics/calendar';
import { computeJournalAnalytics } from './analytics';
import type { TradeRecord } from './types';

function trade(overrides: Partial<TradeRecord>): TradeRecord {
  return {
    id: 't1',
    symbol: 'XAUUSD',
    direction: 'LONG',
    entry: 100,
    exit: 110,
    stopLoss: 95,
    takeProfit: 120,
    quantity: 1,
    entryTime: '2026-09-01T09:30:00.000Z',
    exitTime: '2026-09-01T10:00:00.000Z',
    status: 'closed',
    grossPnl: 10,
    commission: 0,
    fee: 0,
    pnl: 10,
    pnlPct: 0.1,
    rMultiple: 2,
    riskAmount: 5,
    rewardAmount: 20,
    actualRR: 4,
    durationSec: 1800,
    mfe: null,
    mae: null,
    ...overrides,
  };
}

describe('computeTradeMath', () => {
  it('computes P&L, R-multiple and duration for a long', () => {
    const m = computeTradeMath({
      direction: 'LONG', entry: 100, exit: 110, stopLoss: 95, takeProfit: 120, quantity: 2,
      entryTime: '2026-09-01T09:30:00.000Z', exitTime: '2026-09-01T10:00:00.000Z',
    });
    expect(m.pnl).toBe(20);
    expect(m.riskAmount).toBe(10);
    expect(m.rMultiple).toBe(2);
    expect(m.durationSec).toBe(1800);
  });

  it('computes negative R for a losing short', () => {
    const m = computeTradeMath({
      direction: 'SHORT', entry: 100, exit: 110, stopLoss: 105, takeProfit: 90, quantity: 1,
      entryTime: '2026-09-01T09:30:00.000Z', exitTime: '2026-09-01T10:00:00.000Z',
    });
    expect(m.pnl).toBe(-10);
    expect(m.rMultiple).toBe(-2);
  });
});

describe('computePerformance', () => {
  it('computes win rate, net R, expectancy and profit factor', () => {
    const trades = [
      trade({ id: 'a', rMultiple: 2, pnl: 10 }),
      trade({ id: 'b', rMultiple: 1, pnl: 5 }),
      trade({ id: 'c', rMultiple: -1, pnl: -5 }),
      trade({ id: 'd', rMultiple: 0, pnl: 0 }),
    ];
    const p = computePerformance(trades);
    expect(p.totalTrades).toBe(4);
    expect(p.wins).toBe(2);
    expect(p.losses).toBe(1);
    expect(p.breakevens).toBe(1);
    expect(p.winRate).toBe(0.5);
    expect(p.netR).toBe(2);
    expect(p.expectancy).toBe(0.5);
    expect(p.profitFactor).toBe(3);
  });

  it('computes max drawdown from the equity curve', () => {
    const trades = [
      trade({ id: 'a', rMultiple: 2, exitTime: '2026-09-01T10:00:00.000Z' }),
      trade({ id: 'b', rMultiple: -3, exitTime: '2026-09-02T10:00:00.000Z' }),
      trade({ id: 'c', rMultiple: 1, exitTime: '2026-09-03T10:00:00.000Z' }),
    ];
    const p = computePerformance(trades);
    expect(p.maxDrawdown).toBe(3);
  });

  it('classifies trades without an R basis by realized P&L sign', () => {
    // Broker imports have no stop, so riskAmount/rMultiple are empty. A +$50
    // trade must count as a win, not as a zero-R breakeven.
    const trades = [
      trade({ id: 'a', rMultiple: 0, riskAmount: null, pnl: 50 }),
      trade({ id: 'b', rMultiple: 0, riskAmount: null, pnl: -20 }),
      trade({ id: 'c', rMultiple: 0, riskAmount: null, pnl: 0 }),
    ];
    const p = computePerformance(trades);
    expect(p.rAvailable).toBe(false);
    expect(p.wins).toBe(1);
    expect(p.losses).toBe(1);
    expect(p.breakevens).toBe(1);
    expect(p.winRate).toBeCloseTo(1 / 3, 10);
    // Profit factor is currency-based and always meaningful.
    expect(p.profitFactor).toBe(2.5);
    expect(p.netPnl).toBe(30);
  });

  it('reports rAvailable when at least one trade has a stop-derived risk', () => {
    const p = computePerformance([
      trade({ id: 'a', rMultiple: 2, riskAmount: 5, pnl: 10 }),
      trade({ id: 'b', rMultiple: 0, riskAmount: null, pnl: -2 }),
    ]);
    expect(p.rAvailable).toBe(true);
    // Outcome still uses R for the trade that has one, P&L for the other.
    expect(p.wins).toBe(1);
    expect(p.losses).toBe(1);
  });
});

describe('computeDiscipline', () => {
  it('scores a disciplined trader highly', () => {
    const trades = [
      trade({ id: 'a', entry: 100, stopLoss: 99, riskAmount: 1, strategyId: 's1', emotion: 'Calm' }),
      trade({ id: 'b', entry: 100, stopLoss: 99, riskAmount: 1, strategyId: 's1', emotion: 'Focused' }),
    ];
    const d = computeDiscipline(trades);
    expect(d.total).toBeGreaterThan(80);
  });

  it('penalizes missing stops and mistakes', () => {
    const trades = [
      trade({ id: 'a', stopLoss: null, riskAmount: null, strategyId: null, mistakes: '["Early exit","Moved stop"]' }),
    ];
    const d = computeDiscipline(trades);
    expect(d.total).toBeLessThan(50);
  });
});

describe('aggregateDays', () => {
  it('groups trades by day', () => {
    const trades = [
      trade({ id: 'a', rMultiple: 2, exitTime: '2026-09-01T10:00:00.000Z' }),
      trade({ id: 'b', rMultiple: -1, exitTime: '2026-09-01T11:00:00.000Z' }),
      trade({ id: 'c', rMultiple: 3, exitTime: '2026-09-02T10:00:00.000Z' }),
    ];
    const days = aggregateDays(trades);
    expect(days).toHaveLength(2);
    expect(days[0].netR).toBe(1);
    expect(days[1].netR).toBe(3);
  });
});

describe('computeJournalAnalytics', () => {
  it('produces a full analytics bundle', () => {
    const trades = [
      trade({ id: 'a', symbol: 'XAUUSD', session: 'New York', setupName: 'BOS + FVG', emotion: 'Calm', rMultiple: 2 }),
      trade({ id: 'b', symbol: 'NQ', session: 'London', setupName: 'Order Block', emotion: 'FOMO', rMultiple: -1 }),
    ];
    const a = computeJournalAnalytics(trades);
    expect(a.performance.totalTrades).toBe(2);
    expect(a.bySymbol[0].key).toBe('XAUUSD');
    expect(a.bySession[0].key).toBe('New York');
    expect(a.byEmotion[0].key).toBe('Calm');
    expect(a.equity).toHaveLength(2);
  });

  it('groups broker trades by account and magic without dropping manual trades', () => {
    const trades = [
      trade({ id: 'a', accountName: 'Live', magic: 1001, rMultiple: 2 }),
      trade({ id: 'b', accountName: 'Live', magic: 1002, rMultiple: -1 }),
      trade({ id: 'c', accountName: null, magic: null, rMultiple: 1 }),
    ];
    const a = computeJournalAnalytics(trades);
    expect(a.byAccount).toHaveLength(2);
    expect(a.byAccount.find((r) => r.key === 'Live')?.trades).toBe(2);
    expect(a.byAccount.find((r) => r.key === 'Unassigned')?.trades).toBe(1);
    // Manual trades have no magic and are intentionally absent.
    expect(a.byMagic.map((r) => r.key).sort()).toEqual(['1001', '1002']);
  });
});
