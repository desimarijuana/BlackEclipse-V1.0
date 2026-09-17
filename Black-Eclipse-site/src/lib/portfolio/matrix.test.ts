import { describe, it, expect } from 'vitest';
import {
  computeCorrelation, computeRiskMatrix, commonDates, dailyReturns, indexByDate,
  pearson, MIN_OBSERVATIONS, type Series,
} from './matrix';

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Build a Series from a start date and a close list on consecutive weekdays. */
function series(symbol: string, closes: number[], start = '2026-01-05'): Series {
  const dates: string[] = [];
  const d = new Date(`${start}T00:00:00Z`);
  while (dates.length < closes.length) {
    const day = d.getUTCDay();
    if (day !== 0 && day !== 6) dates.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return { symbol, closes, dates };
}

/** Series on explicit dates (for alignment tests). */
function seriesOn(symbol: string, pairs: Array<[string, number]>): Series {
  return { symbol, dates: pairs.map(p => p[0]), closes: pairs.map(p => p[1]) };
}

/** Build a close series from an explicit daily-returns array. */
function closesFromReturns(start: number, returns: number[]): number[] {
  const out = [start];
  for (const r of returns) out.push(out[out.length - 1] * (1 + r));
  return out;
}

// ── indexByDate / alignment ──────────────────────────────────────────────────

describe('indexByDate', () => {
  it('pairs date with close and drops bad pairs TOGETHER', () => {
    // A zero close must not shift every later date onto the wrong close.
    const s: Series = {
      symbol: 'X',
      dates: ['2026-01-05', '2026-01-06', '2026-01-07'],
      closes: [10, 0, 12],
    };
    const m = indexByDate(s);
    expect([...m.keys()]).toEqual(['2026-01-05', '2026-01-07']);
    expect(m.get('2026-01-07')).toBe(12);
  });

  it('ignores non-finite closes and missing dates', () => {
    const s: Series = {
      symbol: 'X',
      dates: ['2026-01-05', '', '2026-01-07'],
      closes: [10, 11, Number.NaN],
    };
    const m = indexByDate(s);
    expect([...m.keys()]).toEqual(['2026-01-05']);
  });

  it('stops at the shorter of closes/dates (never invents a pair)', () => {
    const s: Series = { symbol: 'X', dates: ['a', 'b'], closes: [1, 2, 3] };
    expect(indexByDate(s).size).toBe(2);
  });
});

describe('commonDates', () => {
  it('returns only dates present in EVERY series', () => {
    const a = seriesOn('A', [['2026-01-05', 1], ['2026-01-06', 2], ['2026-01-07', 3]]);
    const b = seriesOn('B', [['2026-01-06', 5], ['2026-01-07', 6], ['2026-01-08', 7]]);
    expect(commonDates([a, b])).toEqual(['2026-01-06', '2026-01-07']);
  });

  it('returns [] when there is no overlap', () => {
    const a = seriesOn('A', [['2026-01-05', 1]]);
    const b = seriesOn('B', [['2026-02-05', 1]]);
    expect(commonDates([a, b])).toEqual([]);
  });

  it('returns [] for an empty input', () => {
    expect(commonDates([])).toEqual([]);
  });
});

// ── Pearson ──────────────────────────────────────────────────────────────────

describe('pearson', () => {
  it('is +1 for a perfectly linear increasing pair', () => {
    expect(pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])).toBeCloseTo(1, 10);
  });

  it('is −1 for a perfectly linear decreasing pair', () => {
    expect(pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])).toBeCloseTo(-1, 10);
  });

  it('returns null when a series never moves (undefined, not 0)', () => {
    expect(pearson([1, 1, 1, 1], [1, 2, 3, 4])).toBeNull();
  });

  it('returns null for fewer than 2 points', () => {
    expect(pearson([1], [2])).toBeNull();
    expect(pearson([], [])).toBeNull();
  });
});

// ── date-aligned correlation ─────────────────────────────────────────────────

describe('computeCorrelation', () => {
  it('returns null with fewer than 2 usable symbols', () => {
    expect(computeCorrelation([])).toBeNull();
    expect(computeCorrelation([series('A', [1, 2, 3, 4, 5])])).toBeNull();
  });

  it('has a unit diagonal and is symmetric', () => {
    const a = series('A', Array.from({ length: 40 }, (_, i) => 100 + Math.sin(i) * 5));
    const b = series('B', Array.from({ length: 40 }, (_, i) => 50 + Math.cos(i) * 3));
    const c = computeCorrelation([a, b])!;
    expect(c.matrix[0][0]).toBe(1);
    expect(c.matrix[1][1]).toBe(1);
    expect(c.matrix[0][1]).toBe(c.matrix[1][0]);
  });

  it('detects a perfectly inverse relationship', () => {
    // Exact inverse returns: r_B = −r_A. (A level series like 200−i does NOT
    // give correlation exactly −1 — its returns are not a scaled negation.)
    const rs = Array.from({ length: 40 }, (_, i) => Math.sin(i / 3) * 0.02);
    const ups = closesFromReturns(100, rs);
    const downs = closesFromReturns(50, rs.map(r => -r));
    const c = computeCorrelation([series('UP', ups), series('DOWN', downs)])!;
    expect(c.matrix[0][1]).toBeCloseTo(-1, 6);
  });

  it('ALIGNS BY DATE, not by index — different trading calendars', () => {
    // A trades Mon/Tue/Wed; B trades Tue/Wed/Thu. Position 0 is a different day
    // for each, so an index-based matrix would compare the wrong observations.
    const a = seriesOn('A', [['2026-01-05', 100], ['2026-01-06', 110], ['2026-01-07', 99]]);
    const b = seriesOn('B', [['2026-01-06', 50], ['2026-01-07', 55], ['2026-01-08', 44]]);
    const c = computeCorrelation([a, b])!;
    // Only 2026-01-06 and 01-07 are shared → 1 return.
    expect(c.observations[0][1]).toBe(1);
    expect(c.symbols).toEqual(['A', 'B']);
  });

  it('reports insufficient overlap as 0 with a low observation count', () => {
    // 3 shared dates → 2 returns, below MIN_OBSERVATIONS.
    const a = series('A', [1, 2, 3]);
    const b = series('B', [3, 2, 1]);
    const c = computeCorrelation([a, b])!;
    expect(c.observations[0][1]).toBeLessThan(MIN_OBSERVATIONS);
    // Shown as no-relationship, but the count makes the weakness visible.
    expect(c.matrix[0][1]).toBe(0);
  });

  it('uses pairwise-complete dates so a short series does not truncate the rest', () => {
    const long1 = series('L1', Array.from({ length: 40 }, (_, i) => 100 + Math.sin(i)));
    const long2 = series('L2', Array.from({ length: 40 }, (_, i) => 100 + Math.cos(i)));
    const short = series('S', Array.from({ length: 6 }, (_, i) => 10 + i));
    const c = computeCorrelation([long1, long2, short])!;
    // The two long series keep their full overlap; the short one does not drag
    // their observation count down.
    expect(c.observations[0][1]).toBeGreaterThanOrEqual(MIN_OBSERVATIONS);
    expect(c.maxObservations).toBeGreaterThanOrEqual(30);
  });

  it('clamps every value into [−1, 1]', () => {
    const a = series('A', Array.from({ length: 50 }, (_, i) => 100 + (i % 7) * 3));
    const b = series('B', Array.from({ length: 50 }, (_, i) => 80 + (i % 5) * 2));
    const c = computeCorrelation([a, b])!;
    for (const row of c.matrix) {
      for (const v of row) {
        expect(v).toBeGreaterThanOrEqual(-1);
        expect(v).toBeLessThanOrEqual(1);
      }
    }
  });
});

// ── Risk decomposition ───────────────────────────────────────────────────────

describe('computeRiskMatrix', () => {
  /** Two uncorrelated-ish series with distinct vols, plus one correlated pair. */
  const mk = () => {
    const seed = (n: number, amp: number, phase: number) =>
      Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i / n + phase) * amp + i * 0.05);
    const a = series('A', seed(3, 5, 0));
    const b = series('B', seed(7, 2, 1.3));
    const c = series('C', seed(3.1, 5, 0.1)); // ~correlated with A
    return [a, b, c];
  };

  it('returns null when weights do not match the correlation symbols', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    expect(computeRiskMatrix(s, [1], corr)).toBeNull();
  });

  it('returns null when all weights are zero', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    expect(computeRiskMatrix(s, [0, 0, 0], corr)).toBeNull();
  });

  it('normalizes weights to sum to 1', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [3, 2, 1], corr)!;
    expect(rm.weights.reduce((a, w) => a + w, 0)).toBeCloseTo(1, 10);
    expect(rm.weights[0]).toBeCloseTo(0.5, 10);
  });

  it('risk contributions sum to 100%', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [1, 1, 1], corr)!;
    expect(rm.riskContributionPct.reduce((a, x) => a + x, 0)).toBeCloseTo(100, 6);
  });

  it('never emits a negative risk share', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [1, 5, 2], corr)!;
    for (const x of rm.riskContributionPct) expect(x).toBeGreaterThanOrEqual(0);
  });

  it('gives a larger risk share to a larger, more volatile position', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    // A dominates in both size and vol → highest contribution.
    const rm = computeRiskMatrix(s, [10, 1, 1], corr)!;
    expect(rm.riskContributionPct[0]).toBeGreaterThan(rm.riskContributionPct[1]);
  });

  it('produces per-holding annualized volatility', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [1, 1, 1], corr)!;
    expect(rm.vol).toHaveLength(3);
    for (const v of rm.vol) expect(v).toBeGreaterThan(0);
    // B was generated with a much smaller amplitude than A.
    expect(rm.vol[1]).toBeLessThan(rm.vol[0]);
  });

  it('reports a diversification benefit between 0 and 100 for imperfect correlation', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [1, 1, 1], corr)!;
    expect(rm.diversificationPct).not.toBeNull();
    expect(rm.diversificationPct!).toBeGreaterThan(-50);
    expect(rm.diversificationPct!).toBeLessThan(99);
  });

  it('gives ~0% diversification when holdings move identically', () => {
    // Same shape, different scale → correlation 1 → no risk removed.
    const base = Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i / 4) * 8 + i * 0.1);
    const a = series('A', base);
    const b = series('B', base.map(x => x * 2));
    const corr = computeCorrelation([a, b])!;
    const rm = computeRiskMatrix([a, b], [1, 1], corr)!;
    expect(rm.diversificationPct!).toBeLessThan(1);
  });

  it('reports the median pairwise overlap as the observation count', () => {
    const s = mk();
    const corr = computeCorrelation(s)!;
    const rm = computeRiskMatrix(s, [1, 1, 1], corr)!;
    expect(rm.observations).toBeGreaterThan(0);
  });
});

// ── dailyReturns ─────────────────────────────────────────────────────────────

describe('dailyReturns', () => {
  it('computes simple returns and skips non-positive bases', () => {
    expect(dailyReturns([100, 110])[0]).toBeCloseTo(0.1, 12);
    expect(dailyReturns([0, 5])).toEqual([]);
    expect(dailyReturns([10])).toEqual([]);
  });

  it('is insensitive to the absolute price level (currency-neutral)', () => {
    // The same asset quoted in two currencies has identical returns — this is
    // why correlations are correct for a mixed-currency book without FX.
    const native = [100, 110, 121, 133.1];
    const converted = native.map(x => x * 278);
    expect(dailyReturns(converted).map(r => +r.toFixed(10)))
      .toEqual(dailyReturns(native).map(r => +r.toFixed(10)));
  });
});
