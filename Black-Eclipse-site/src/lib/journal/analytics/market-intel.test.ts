import { describe, it, expect } from 'vitest';
import { computeMfeMae } from './mfe-mae';
import { computeMarketContext } from './market-context';
import { similarityScore, findSimilarTrades } from './similarity';
import type { TradeRecord } from '../types';
import type { PricePoint } from './mfe-mae';

function bar(date: string, o: number, h: number, l: number, c: number, v = 1000): PricePoint {
  return { date, open: o, high: h, low: l, close: c, volume: v };
}

function trade(overrides: Partial<TradeRecord>): TradeRecord {
  return {
    id: 't1', symbol: 'XAUUSD', direction: 'LONG', entry: 100, exit: 110,
    stopLoss: 99, takeProfit: 120, quantity: 1,
    entryTime: '2026-09-01T09:30:00.000Z', exitTime: '2026-09-01T10:00:00.000Z',
    status: 'closed', grossPnl: 10, commission: 0, fee: 0, pnl: 10, pnlPct: 0.1, rMultiple: 2, riskAmount: 1,
    rewardAmount: 21, actualRR: 2.1, durationSec: 1800, mfe: null, mae: null,
    emotion: 'Calm', confidence: 4, session: 'New York', timeframe: '15m', marketRegime: 'Trending',
    ...overrides,
  };
}

describe('computeMfeMae', () => {
  it('computes MFE and MAE in R for a long', () => {
    const series = [
      bar('2026-09-01', 100, 101, 99, 100),
      bar('2026-09-01', 100, 103, 99.5, 102), // MFE high 103 = +3R
      bar('2026-09-01', 102, 102, 98.5, 99),  // MAE low 98.5 = -1.5R
      bar('2026-09-01', 99, 110, 99, 110),   // exit
    ];
    const r = computeMfeMae(series, 100, 99, 'LONG', '2026-09-01T00:00:00.000Z', '2026-09-01T23:59:00.000Z');
    expect(r.mfe).toBeCloseTo(10, 1); // exit bar high 110 = +10R
    expect(r.mae).toBeCloseTo(-1.5, 1);
  });

  it('returns nulls without a stop', () => {
    const r = computeMfeMae([bar('2026-09-01', 100, 101, 99, 100)], 100, null, 'LONG', '2026-09-01T09:30:00.000Z', '2026-09-01T10:00:00.000Z');
    expect(r.mfe).toBeNull();
    expect(r.mae).toBeNull();
  });
});

describe('computeMarketContext', () => {
  it('detects a bullish trend', () => {
    const series: PricePoint[] = [];
    for (let i = 0; i < 60; i++) {
      const c = 100 + i * 0.5;
      series.push(bar(`2026-08-${String((i % 28) + 1).padStart(2, '0')}`, c - 1, c + 1, c - 1, c));
    }
    const ctx = computeMarketContext(series, 120, '2026-09-01T09:30:00.000Z');
    expect(ctx.trend).toBe('Bullish');
    expect(ctx.regime).toBeDefined();
  });
});

describe('similarityScore', () => {
  it('scores identical trades highest', () => {
    const a = trade({ id: 'a', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish' });
    const b = trade({ id: 'b', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish' });
    expect(similarityScore(a, b)).toBeGreaterThan(0.8);
  });

  it('scores different symbols lower', () => {
    const a = trade({ id: 'a', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish' });
    const b = trade({ id: 'b', symbol: 'NQ', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish' });
    expect(similarityScore(a, b)).toBeLessThan(similarityScore(a, { ...b, symbol: 'XAUUSD' }));
  });
});

describe('findSimilarTrades', () => {
  it('returns similar trades with aggregate stats', () => {
    const target = trade({ id: 't', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish' });
    const others = [
      trade({ id: 'a', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish', rMultiple: 2 }),
      trade({ id: 'b', symbol: 'XAUUSD', direction: 'LONG', setupName: 'BOS + FVG', session: 'New York', timeframe: '15m', marketRegime: 'Trending', trend: 'Bullish', rMultiple: -1 }),
      trade({ id: 'c', symbol: 'BTCUSD', direction: 'SHORT', setupName: 'Breakout', session: 'Asia', timeframe: '1h', marketRegime: 'Ranging', trend: 'Bearish', rMultiple: 3 }),
    ];
    const result = findSimilarTrades(target, [target, ...others], 10, 0.2);
    expect(result.count).toBe(2);
    expect(result.winRate).toBe(0.5);
    expect(result.averageR).toBe(0.5);
  });
});
