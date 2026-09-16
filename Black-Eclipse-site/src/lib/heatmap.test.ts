import { describe, it, expect } from 'vitest';
import {
  summarizeVolume, turnoverFor, isNotionalVolume,
  type VolumeInput,
} from './heatmap';

// ── Unit semantics ───────────────────────────────────────────────────────────
// The core honesty problem this module exists to solve: JDDS stores crypto
// volume as quote-currency NOTIONAL but equity volume as a SHARE COUNT.
// Multiplying a notional by price double-counts; not multiplying a share count
// makes the value meaningless. These tests pin that contract.

describe('isNotionalVolume', () => {
  it('treats crypto as quote-currency notional', () => {
    expect(isNotionalVolume('CRYPTO')).toBe(true);
  });
  it('treats equities as share counts', () => {
    for (const m of ['US', 'PK', 'IN', 'DE', 'JP']) {
      expect(isNotionalVolume(m)).toBe(false);
    }
  });
});

describe('turnoverFor', () => {
  it('returns notional unchanged for crypto (no price multiply)', () => {
    expect(turnoverFor(1_000_000, 75_000, 'CRYPTO')).toBe(1_000_000);
  });
  it('multiplies shares by price for equities', () => {
    expect(turnoverFor(1_000, 25, 'US')).toBe(25_000);
  });
  it('returns 0 for non-positive volume', () => {
    expect(turnoverFor(0, 100, 'US')).toBe(0);
    expect(turnoverFor(-5, 100, 'US')).toBe(0);
  });
});

// ── summarizeVolume ──────────────────────────────────────────────────────────

function row(symbol: string, volume: number, price: number, changePct = 0): VolumeInput {
  return { symbol, name: `${symbol} Inc.`, sector: 'Tech', price, volume, changePct };
}

describe('summarizeVolume', () => {
  it('returns null when nothing has positive volume', () => {
    expect(summarizeVolume([row('A', 0, 10), row('B', 0, 20)], 'US', '$')).toBeNull();
  });

  it('returns null for an empty list', () => {
    expect(summarizeVolume([], 'US', '$')).toBeNull();
  });

  it('computes turnover, shares and concentration for equities', () => {
    // Turnovers: A=100*10=1000, B=100*20=2000, C=100*30=3000 → total 6000.
    const s = summarizeVolume(
      [row('A', 100, 10), row('B', 100, 20), row('C', 100, 30)],
      'US', '$',
    )!;
    expect(s.unit).toBe('shares');
    expect(s.currency).toBe('$');
    expect(s.instruments).toBe(3);
    expect(s.turnover).toBe(6000);
    expect(s.totalVolume).toBe(300);
    expect(s.maxTurnover).toBe(3000);
    expect(s.medianTurnover).toBe(2000);
    expect(s.averageTurnover).toBe(2000);
    // Shares: C=50%, B=33.33%, A=16.67%.
    expect(s.top[0].symbol).toBe('C');
    expect(s.top[0].sharePct).toBeCloseTo(50, 5);
    expect(s.top10SharePct).toBeCloseTo(100, 5);
    // HHI = 50² + 33.33² + 16.67² ≈ 3888.9.
    expect(s.hhi).toBeCloseTo(3888.9, 0);
  });

  it('does not multiply crypto notional by price', () => {
    const s = summarizeVolume(
      [row('BTC', 1_000_000, 75_000, 1), row('ETH', 500_000, 2_500, -1)],
      'CRYPTO', '$',
    )!;
    expect(s.unit).toBe('notional');
    // Turnover is the notional itself — NOT 1e6 * 75000.
    expect(s.turnover).toBe(1_500_000);
    expect(s.totalVolume).toBe(1_500_000);
  });

  it('excludes zero-volume and zero-price rows from the analysis', () => {
    const s = summarizeVolume(
      [row('A', 100, 10), row('B', 0, 20), row('C', 100, 0)],
      'US', '$',
    )!;
    expect(s.instruments).toBe(1);
    // marketAssets still counts every row the caller supplied.
    expect(s.marketAssets).toBe(3);
    expect(s.top).toHaveLength(1);
  });

  it('buckets instruments into contiguous contribution bands', () => {
    // Turnovers: D=800 (80%), C=150 (15%), B=40 (4%), A=10 (1%) → total 1000.
    const s = summarizeVolume(
      [row('A', 1, 10), row('B', 2, 20), row('C', 3, 50), row('D', 4, 200)],
      'US', '$',
    )!;
    const byLabel = Object.fromEntries(s.tiers.map(t => [t.label, t]));
    expect(byLabel['Dominant (≥10%)'].count).toBe(2); // D 80% + C 15%
    expect(byLabel['Dominant (≥10%)'].sharePct).toBeCloseTo(95, 5);
    expect(byLabel['Major (2–10%)'].count).toBe(1); // B 4%
    expect(byLabel['Major (2–10%)'].sharePct).toBeCloseTo(4, 5);
    expect(byLabel['Minor (<0.5%)'].count).toBe(0);
    // Bands must sum to the whole market.
    const totalShare = s.tiers.reduce((a, t) => a + t.sharePct, 0);
    expect(totalShare).toBeCloseTo(100, 5);
    const totalCount = s.tiers.reduce((a, t) => a + t.count, 0);
    expect(totalCount).toBe(4);
  });

  it('caps top contributors but keeps the full distribution in the stats', () => {
    const rows = Array.from({ length: 30 }, (_, i) => row(`S${i}`, 1000 - i, 10));
    const s = summarizeVolume(rows, 'US', '$')!;
    expect(s.instruments).toBe(30);
    // VOLUME_TOP_N is 12.
    expect(s.top).toHaveLength(12);
    expect(s.top[0].symbol).toBe('S0');
    // Median comes from all 30, not the truncated top list.
    expect(s.medianTurnover).toBeGreaterThan(0);
  });

  it('orders top contributors by turnover, not raw volume', () => {
    // LOW has the bigger share count but the smaller traded value.
    const s = summarizeVolume(
      [row('BIG', 10, 1_000), row('LOW', 500, 2)],
      'US', '$',
    )!;
    expect(s.top[0].symbol).toBe('BIG');
    expect(s.tiers[0].count).toBe(1);
  });

  it('flags a concentrated market via a high HHI', () => {
    const s = summarizeVolume(
      [row('WHALE', 10_000, 100), ...Array.from({ length: 50 }, (_, i) => row(`x${i}`, 1, 1))],
      'US', '$',
    )!;
    expect(s.hhi).toBeGreaterThan(2500);
    expect(s.top10SharePct).toBeGreaterThan(99);
  });

  it('reports a low HHI for an evenly spread market', () => {
    const rows = Array.from({ length: 100 }, (_, i) => row(`S${i}`, 100, 10));
    const s = summarizeVolume(rows, 'US', '$')!;
    // 100 equal instruments → HHI = 100 * 1² = 100.
    expect(s.hhi).toBeCloseTo(100, 5);
  });

  it('carries the market currency through to the summary', () => {
    const s = summarizeVolume([row('A', 100, 10)], 'PK', 'PKR')!;
    expect(s.currency).toBe('PKR');
  });
});
