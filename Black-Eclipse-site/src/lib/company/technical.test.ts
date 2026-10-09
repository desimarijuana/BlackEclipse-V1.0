import { describe, it, expect } from 'vitest';
import type { PriceBar } from '@/lib/chart/types';
import { computeTechnical } from './technical';

function bars(closes: number[], withVolume = true): PriceBar[] {
  return closes.map((c, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, '0')}`,
    open: c, high: c, low: c, close: c,
    volume: withVolume ? 1000 + i : null,
  }));
}

describe('computeTechnical', () => {
  it('returns an all-null snapshot for empty input (never fabricated)', () => {
    const t = computeTechnical([]);
    expect(t.bars).toBe(0);
    expect(t.last).toBeNull();
    expect(t.trend).toBe('unknown');
    expect(t.rsiState).toBe('unknown');
  });

  it('classifies an uptrend when price leads a rising average', () => {
    const rising = Array.from({ length: 220 }, (_, i) => 100 + i);
    const t = computeTechnical(bars(rising));
    expect(t.bars).toBe(220);
    expect(t.trend).toBe('uptrend');
    expect(t.sma50).not.toBeNull();
    expect(t.return1m).toBeGreaterThan(0);
  });

  it('classifies a downtrend on a falling series', () => {
    const falling = Array.from({ length: 220 }, (_, i) => 300 - i);
    const t = computeTechnical(bars(falling));
    expect(t.trend).toBe('downtrend');
    expect(t.maxDrawdownPct).toBeLessThan(0);
  });

  it('computes RSI, MACD and volatility from real data', () => {
    const series = Array.from({ length: 120 }, (_, i) => 100 + Math.sin(i / 5) * 10);
    const t = computeTechnical(bars(series));
    expect(t.rsi14).not.toBeNull();
    expect(t.macd).not.toBeNull();
    expect(t.macdState === 'bullish' || t.macdState === 'bearish').toBe(true);
    expect(t.volatilityPct).not.toBeNull();
    expect(t.atr14).not.toBeNull();
  });

  it('reports volume trend only when volume exists', () => {
    const series = Array.from({ length: 60 }, (_, i) => 100 + i);
    expect(computeTechnical(bars(series, false)).volumeTrend).toBeNull();
    expect(computeTechnical(bars(series, true)).volumeTrend).toBeGreaterThan(0);
  });

  it('flags overbought RSI on a straight-up series', () => {
    const rising = Array.from({ length: 60 }, (_, i) => 100 + i * 2);
    expect(computeTechnical(bars(rising)).rsiState).toBe('overbought');
  });
});
