import { describe, it, expect } from 'vitest';
import { intensityFor } from './intensity';

// ── Calendar intensity buckets ───────────────────────────────────────────────
// The mini calendar's colour must distinguish a big day from a small one, and
// must never collapse a loss into a profit colour (or vice versa). These pin the
// bucket boundaries and the sign, which is what makes the grid readable.

describe('intensityFor', () => {
  it('marks a zero net R as flat, not profit', () => {
    expect(intensityFor(0)).toEqual({ level: 0, sign: 'zero' });
  });

  it('signs positive days positive and negative days negative', () => {
    expect(intensityFor(0.1).sign).toBe('pos');
    expect(intensityFor(-0.1).sign).toBe('neg');
    // The sign must never flip on a near-zero loss.
    expect(intensityFor(-0.001).sign).toBe('neg');
    expect(intensityFor(0.001).sign).toBe('pos');
  });

  it('buckets by absolute magnitude so bigger moves read stronger', () => {
    // <1R
    expect(intensityFor(0.5).level).toBe(1);
    expect(intensityFor(-0.99).level).toBe(1);
    // 1–2R
    expect(intensityFor(1).level).toBe(2);
    expect(intensityFor(1.99).level).toBe(2);
    // 2–3R
    expect(intensityFor(2).level).toBe(3);
    expect(intensityFor(2.99).level).toBe(3);
    // >=3R
    expect(intensityFor(3).level).toBe(4);
    expect(intensityFor(-7.5).level).toBe(4);
  });

  it('treats +R and −R of the same magnitude as the same level', () => {
    for (const v of [0.4, 1.2, 2.5, 4.0]) {
      expect(intensityFor(v).level).toBe(intensityFor(-v).level);
      expect(intensityFor(v).sign).not.toBe(intensityFor(-v).sign);
    }
  });

  it('is monotonic in magnitude within a sign', () => {
    const pos = [0.1, 0.9, 1.5, 2.5, 5].map((v) => intensityFor(v).level);
    for (let i = 1; i < pos.length; i++) expect(pos[i]).toBeGreaterThanOrEqual(pos[i - 1]);
  });
});
