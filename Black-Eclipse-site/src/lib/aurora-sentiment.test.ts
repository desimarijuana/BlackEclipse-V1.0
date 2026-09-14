import { describe, it, expect } from 'vitest';
import {
  auroraSentiment,
  classifyAuroraState,
  combineSentiment,
  marketSentimentFromIndices,
  mixHex,
  normalizeMarketSentiment,
  resolveAuroraVisuals,
  stepSentiment,
} from './aurora-sentiment';

// Index fixtures — the real /api/indices card shape (price + changePercent).
const eq = (symbol: string, changePercent: number) => ({
  symbol,
  price: 100 + changePercent,
  changePercent,
});

describe('normalizeMarketSentiment', () => {
  it('maps a flat market to 0', () => {
    expect(normalizeMarketSentiment(0)).toBe(0);
  });

  it('keeps the sign and compresses outliers into [-1, 1]', () => {
    expect(normalizeMarketSentiment(1.5)).toBeGreaterThan(0.7);
    expect(normalizeMarketSentiment(1.5)).toBeLessThan(1);
    expect(normalizeMarketSentiment(-1.5)).toBeLessThan(-0.7);
    expect(normalizeMarketSentiment(100)).toBeLessThanOrEqual(1);
    expect(normalizeMarketSentiment(-100)).toBeGreaterThanOrEqual(-1);
  });

  it('handles non-finite input', () => {
    expect(normalizeMarketSentiment(NaN)).toBe(0);
    expect(normalizeMarketSentiment(Infinity)).toBe(0);
  });
});

describe('marketSentimentFromIndices', () => {
  it('returns null when no priced index data is available', () => {
    expect(marketSentimentFromIndices(null, null)).toBeNull();
    expect(marketSentimentFromIndices([], [])).toBeNull();
    // Zero-price placeholder cards are not real data.
    expect(marketSentimentFromIndices([{ symbol: '^GSPC', price: 0, changePercent: 0 }], [])).toBeNull();
  });

  it('is bullish when equities are broadly up', () => {
    const s = marketSentimentFromIndices(
      [eq('^GSPC', 1.2), eq('^IXIC', 1.1), eq('^DJI', 0.9)],
      [{ change: 1 }, { change: 2 }, { change: 0.5 }],
    );
    expect(s).toBeGreaterThan(0.35);
  });

  it('is bearish when equities are broadly down', () => {
    const s = marketSentimentFromIndices(
      [eq('^GSPC', -1.2), eq('^IXIC', -1.0), eq('^DJI', -0.9)],
      [{ change: -1 }, { change: -2 }, { change: -0.5 }],
    );
    expect(s).toBeLessThan(-0.35);
  });

  it('excludes crypto/commodity hedges that invert on risk-off days', () => {
    // Every stock index is red, but gold is up big. The hedge must be excluded
    // so the reading stays bearish instead of flipping green.
    const s = marketSentimentFromIndices(
      [eq('^GSPC', -1.5), eq('^IXIC', -1.4), eq('GC=F', 2.5)],
      [],
    );
    expect(s).toBeLessThan(0);
    expect(s).toBeLessThan(-0.35);
  });

  it('falls back to all priced indices if no equity indices exist', () => {
    const s = marketSentimentFromIndices([eq('GC=F', 3)], []);
    expect(s).toBeGreaterThan(0);
  });
});

describe('combineSentiment', () => {
  it('weights market 60% / news 40%', () => {
    expect(combineSentiment(1, 0)).toBeCloseTo(0.6, 5);
    expect(combineSentiment(0, 1)).toBeCloseTo(0.4, 5);
    expect(combineSentiment(1, 1)).toBeCloseTo(1, 5);
    expect(combineSentiment(-1, -1)).toBeCloseTo(-1, 5);
  });

  it('renormalizes when one side is missing (never invents a signal)', () => {
    expect(combineSentiment(null, 0.8)).toBeCloseTo(0.8, 5);
    expect(combineSentiment(0.8, null)).toBeCloseTo(0.8, 5);
    expect(combineSentiment(undefined, -0.5)).toBeCloseTo(-0.5, 5);
  });

  it('returns neutral when both sides are unavailable', () => {
    expect(combineSentiment(null, null)).toBe(0);
    expect(combineSentiment(NaN, undefined)).toBe(0);
  });

  it('clamps out-of-range inputs defensively', () => {
    expect(combineSentiment(5, 5)).toBe(1);
    expect(combineSentiment(-5, -5)).toBe(-1);
  });
});

describe('classifyAuroraState', () => {
  it('uses the ±0.35 thresholds', () => {
    expect(classifyAuroraState(0.35)).toBe('bullish');
    expect(classifyAuroraState(0.2)).toBe('neutral');
    expect(classifyAuroraState(0)).toBe('neutral');
    expect(classifyAuroraState(-0.2)).toBe('neutral');
    expect(classifyAuroraState(-0.35)).toBe('bearish');
  });
});

describe('auroraSentiment (end-to-end)', () => {
  it('Test 1: market +1, news +1 → bullish green', () => {
    const a = auroraSentiment(1, 1);
    expect(a.score).toBeCloseTo(1, 5);
    expect(a.state).toBe('bullish');
    expect(resolveAuroraVisuals(a.score).colorStops[1].toLowerCase()).toBe('#7aff78');
  });

  it('Test 2: market -1, news -1 → bearish red', () => {
    const a = auroraSentiment(-1, -1);
    expect(a.score).toBeCloseTo(-1, 5);
    expect(a.state).toBe('bearish');
    expect(resolveAuroraVisuals(a.score).colorStops[1].toLowerCase()).toBe('#ff3e3e');
  });

  it('Test 3: market 0, news 0 → neutral (subdued green, not purple)', () => {
    const a = auroraSentiment(0, 0);
    expect(a.score).toBe(0);
    expect(a.state).toBe('neutral');
    const v = resolveAuroraVisuals(a.score);
    expect(v.state).toBe('neutral');
    expect(v.colorStops[1].toLowerCase()).toBe('#3d9e63');
  });

  it('Test 4: market +0.8, news -0.7 → mixed, near-neutral', () => {
    const a = auroraSentiment(0.8, -0.7);
    expect(a.score).toBeCloseTo(0.8 * 0.6 + -0.7 * 0.4, 3);
    expect(a.score).toBeCloseTo(0.2, 3);
    expect(a.state).toBe('neutral');
    expect(Math.abs(a.score)).toBeLessThan(0.35);
  });

  it('Test 5: missing news data stays functional', () => {
    const a = auroraSentiment(0.9, null);
    expect(Number.isFinite(a.score)).toBe(true);
    expect(a.state).toBe('bullish');
  });

  it('Test 6: missing market sentiment stays functional', () => {
    const a = auroraSentiment(null, -0.9);
    expect(Number.isFinite(a.score)).toBe(true);
    expect(a.state).toBe('bearish');
  });

  it('Test 6b: all missing never reads bullish', () => {
    expect(auroraSentiment(null, null).state).toBe('neutral');
    expect(auroraSentiment(undefined, undefined).score).toBe(0);
  });
});

describe('resolveAuroraVisuals', () => {
  it('interpolates colors continuously (no abrupt switch)', () => {
    const near = resolveAuroraVisuals(0.05).colorStops[1];
    const mid = resolveAuroraVisuals(0.5).colorStops[1];
    const far = resolveAuroraVisuals(1).colorStops[1];
    expect(near).not.toBe(mid);
    expect(mid).not.toBe(far);
    // Subdued green neutral center vs. bright bullish green center.
    expect(mixHex('#3d9e63', '#7aff78', 0)).toBe('#3d9e63');
  });

  it('never emits a purple/neutral hue that departs the green/red brand palette', () => {
    // Every resolved center must be either green-dominant (neutral/bullish) or
    // red-dominant (bearish) — never a blue/purple mix.
    for (const s of [-1, -0.5, -0.2, 0, 0.2, 0.5, 1]) {
      const hex = resolveAuroraVisuals(s).colorStops[1].replace('#', '');
      const r = parseInt(hex.slice(0, 2), 16);
      const g = parseInt(hex.slice(2, 4), 16);
      const b = parseInt(hex.slice(4, 6), 16);
      expect(b).toBeLessThanOrEqual(Math.max(r, g));
      expect(g).toBeGreaterThanOrEqual(b);
    }
  });

  it('keeps motion subtle and bounded', () => {
    const calm = resolveAuroraVisuals(0);
    const strong = resolveAuroraVisuals(1);
    expect(calm.amplitude).toBeCloseTo(1.2, 5);
    expect(strong.amplitude).toBeCloseTo(1.8, 5);
    expect(strong.speed).toBeGreaterThan(calm.speed);
    expect(strong.speed).toBeLessThanOrEqual(2);
  });

  it('handles NaN as neutral', () => {
    expect(resolveAuroraVisuals(NaN).state).toBe('neutral');
  });
});

describe('stepSentiment (smoothing)', () => {
  it('moves a fraction of the way toward the target (no flicker)', () => {
    const s1 = stepSentiment(0.25, 0.22, 0.1);
    expect(s1).toBeGreaterThan(0.22);
    expect(s1).toBeLessThan(0.25);
    const s2 = stepSentiment(0.03, -0.02, 0.1);
    expect(s2).toBeGreaterThan(-0.02);
    expect(s2).toBeLessThan(0.03);
  });

  it('converges to the target over repeated steps', () => {
    let s = 0;
    for (let i = 0; i < 200; i++) s = stepSentiment(s, -0.6, 0.1);
    expect(s).toBeCloseTo(-0.6, 2);
  });

  it('clamps alpha and non-finite inputs', () => {
    expect(stepSentiment(0, 1, 2)).toBe(1);
    expect(stepSentiment(NaN, 1, 0.5)).toBe(0.5);
  });
});
