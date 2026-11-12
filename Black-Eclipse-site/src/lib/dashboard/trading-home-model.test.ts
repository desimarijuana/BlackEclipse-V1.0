import { describe, expect, it } from 'vitest';
import type { BrokerAccount, BrokerFill, BrokerPosition } from '@/lib/harness/clients/trading-client';
import {
  buildDailyRealized,
  computeExposure,
  computeTodayPnl,
  marginHealth,
  startOfLocalDay,
  trimSeries,
} from './trading-home-model';

const fill = (overrides: Partial<BrokerFill>): BrokerFill => ({
  dealTicket: 1,
  orderTicket: null,
  positionTicket: null,
  symbol: 'EURUSD',
  side: 'buy',
  entry: 'out',
  volume: 0.1,
  price: 1.1,
  commission: 0,
  swap: 0,
  profit: 0,
  magic: 0,
  comment: null,
  dealtAt: Date.now(),
  eclipseOwned: false,
  syncedAt: new Date().toISOString(),
  ...overrides,
});

const position = (overrides: Partial<BrokerPosition>): BrokerPosition => ({
  ticket: 1,
  symbol: 'EURUSD',
  side: 'buy',
  volume: 0.1,
  openPrice: 1.1,
  currentPrice: 1.1,
  stopLoss: null,
  takeProfit: null,
  profit: 0,
  swap: 0,
  magic: 0,
  comment: '',
  openedAt: Date.now(),
  ...overrides,
});

const account = (overrides: Partial<BrokerAccount>): BrokerAccount => ({
  login: 123,
  mode: 'demo',
  server: 'Demo',
  company: 'Broker',
  currency: 'USD',
  balance: 10_000,
  equity: 10_000,
  margin: 500,
  marginFree: 9_500,
  marginLevel: 2000,
  profit: 0,
  leverage: 100,
  marginMode: 'hedging',
  tradeAllowed: true,
  expertAllowed: true,
  ...overrides,
});

describe('startOfLocalDay', () => {
  it('returns local midnight for the given instant', () => {
    const now = new Date(2026, 10, 4, 15, 30, 45).getTime();
    const start = new Date(startOfLocalDay(now));
    expect(start.getHours()).toBe(0);
    expect(start.getMinutes()).toBe(0);
    expect(start.getSeconds()).toBe(0);
    expect(start.getDate()).toBe(new Date(now).getDate());
  });
});

describe('computeTodayPnl', () => {
  const day = new Date(2026, 10, 4, 12, 0, 0).getTime();
  const start = startOfLocalDay(day);

  it('sums broker deals since local midnight only', () => {
    const fills = [
      fill({ dealTicket: 1, dealtAt: start + 1_000, profit: 100, swap: -2, commission: -5 }),
      fill({ dealTicket: 2, dealtAt: start + 2_000, profit: -40 }),
      fill({ dealTicket: 3, dealtAt: start - 1, profit: 999 }), // yesterday — excluded
    ];
    const pnl = computeTodayPnl(fills, 12.5, day);
    expect(pnl.realized).toBeCloseTo(53);
    expect(pnl.floating).toBeCloseTo(12.5);
    expect(pnl.total).toBeCloseTo(65.5);
    expect(pnl.dealCount).toBe(2);
  });

  it('treats a missing floating profit as zero, never as NaN', () => {
    const pnl = computeTodayPnl([], null, day);
    expect(pnl.total).toBe(0);
    expect(pnl.floating).toBe(0);
  });

  it('ignores fills with non-finite timestamps', () => {
    const pnl = computeTodayPnl([fill({ dealtAt: Number.NaN, profit: 500 })], 0, day);
    expect(pnl.realized).toBe(0);
    expect(pnl.dealCount).toBe(0);
  });
});

describe('marginHealth', () => {
  it('bands broker-reported margin level', () => {
    expect(marginHealth(null)).toBe('unavailable');
    expect(marginHealth(Number.NaN)).toBe('unavailable');
    expect(marginHealth(500)).toBe('healthy');
    expect(marginHealth(150)).toBe('healthy');
    expect(marginHealth(149.9)).toBe('watch');
    expect(marginHealth(100)).toBe('watch');
    expect(marginHealth(99.9)).toBe('danger');
  });
});

describe('computeExposure', () => {
  it('aggregates per symbol and sorts by absolute profit', () => {
    const positions = [
      position({ ticket: 1, symbol: 'EURUSD', volume: 0.3, profit: 10 }),
      position({ ticket: 2, symbol: 'EURUSD', volume: 0.2, profit: 15 }),
      position({ ticket: 3, symbol: 'XAUUSD', volume: 0.1, profit: -200 }),
    ];
    const summary = computeExposure(positions, account({}));
    expect(summary.openCount).toBe(3);
    expect(summary.netFloating).toBeCloseTo(-175);
    expect(summary.grossAbsFloating).toBeCloseTo(225);
    expect(summary.bySymbol[0].symbol).toBe('XAUUSD');
    expect(summary.bySymbol[1].symbol).toBe('EURUSD');
    expect(summary.bySymbol[1].volume).toBeCloseTo(0.5);
    expect(summary.bySymbol[1].profit).toBeCloseTo(25);
  });

  it('computes margin usage as a percentage of equity', () => {
    const summary = computeExposure([], account({ margin: 2_000, equity: 10_000 }));
    expect(summary.marginUsagePct).toBeCloseTo(20);
  });

  it('returns null margin fields instead of fabricating them', () => {
    expect(computeExposure([], null).marginUsagePct).toBeNull();
    expect(computeExposure([], null).marginLevel).toBeNull();
    expect(computeExposure([], account({ equity: 0, margin: 100 })).marginUsagePct).toBeNull();
    expect(computeExposure([], null).grossAbsFloating).toBeNull();
    expect(computeExposure([], null).bySymbol).toEqual([]);
  });
});

describe('buildDailyRealized', () => {
  const day = new Date(2026, 10, 4, 12, 0, 0).getTime(); // 2026-11-04 local noon

  it('returns one point per day, ending today, carrying values forward', () => {
    const fills = [
      fill({ dealTicket: 1, dealtAt: startOfLocalDay(day) + 3_600_000, profit: 100 }),
      fill({ dealTicket: 2, dealtAt: startOfLocalDay(day) - 86_400_000 + 1_000, profit: 50 }),
    ];
    const series = buildDailyRealized(fills, day, 3);
    expect(series.points).toHaveLength(3);
    expect(series.dealCount).toBe(2);
    expect(series.points[0].value).toBeCloseTo(0);
    expect(series.points[1].value).toBeCloseTo(50);
    expect(series.points[2].value).toBeCloseTo(150);
    expect(series.points[2].day).toBe('2026-11-04');
  });

  it('ignores deals older than the window', () => {
    const fills = [fill({ dealTicket: 1, dealtAt: startOfLocalDay(day) - 10 * 86_400_000, profit: 999 })];
    const series = buildDailyRealized(fills, day, 7);
    expect(series.dealCount).toBe(0);
    expect(series.points.every((point) => point.value === 0)).toBe(true);
  });

  it('includes profit, swap and commission', () => {
    const fills = [
      fill({ dealTicket: 1, dealtAt: startOfLocalDay(day) + 1_000, profit: 100, swap: -4, commission: -6 }),
    ];
    const series = buildDailyRealized(fills, day, 2);
    expect(series.points[series.points.length - 1].value).toBeCloseTo(90);
  });

  it('clamps the window to at least two days and copes with no fills', () => {
    const series = buildDailyRealized([], day, 1);
    expect(series.points).toHaveLength(2);
    expect(series.dealCount).toBe(0);
  });
});

describe('trimSeries', () => {
  it('keeps the most recent points', () => {
    expect(trimSeries([1, 2, 3, 4, 5], 3)).toEqual([3, 4, 5]);
    expect(trimSeries([1, 2], 5)).toEqual([1, 2]);
    expect(trimSeries([1, 2], 0)).toEqual([]);
  });
});
