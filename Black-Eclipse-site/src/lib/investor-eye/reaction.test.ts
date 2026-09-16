import { describe, it, expect } from 'vitest';
import { computePriceReaction, eventDay, reactionWindowLabel, daysBetween, REACTION_WINDOWS } from './reaction';
import type { PricePoint } from './reaction';

/** Build a series of consecutive UTC days starting at `start`. */
function series(start: string, closes: number[]): PricePoint[] {
  const t0 = Date.parse(`${start}T00:00:00Z`);
  return closes.map((v, i) => ({
    date: new Date(t0 + i * 86400000).toISOString().slice(0, 10),
    value: v,
  }));
}

describe('eventDay', () => {
  it('parses ISO timestamps to a UTC day', () => {
    expect(eventDay('2026-03-05T14:22:00.000Z')).toBe('2026-03-05');
  });
  it('rejects unparseable input', () => {
    expect(eventDay('not-a-date')).toBeNull();
  });
});

describe('computePriceReaction', () => {
  it('measures returns against the last close on or before the event', () => {
    // 10 days at 100, then a jump to 110 the day after the event.
    const s = series('2026-03-01', [100, 100, 100, 110, 100, 100, 100, 100, 100, 100]);
    const r = computePriceReaction('^GSPC', '2026-03-03T12:00:00Z', s);
    // Baseline is 2026-03-03 (the day of the event, on or before).
    expect(r.baseline?.date).toBe('2026-03-03');
    const one = r.measures.find((m) => m.window === 1);
    expect(one?.changePct).toBeCloseTo(10, 3);
    expect(r.maxAbsChangePct).toBeCloseTo(10, 3);
    expect(r.availability).toBe('HISTORICAL');
  });

  it('reports a negative move with the correct sign', () => {
    const s = series('2026-03-01', [100, 100, 100, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90]);
    const r = computePriceReaction('^GSPC', '2026-03-03T00:00:00Z', s);
    expect(r.measures.find((m) => m.window === 1)?.changePct).toBeCloseTo(-10, 3);
  });

  it('returns UNAVAILABLE with a reason when history starts after the event', () => {
    const s = series('2026-06-01', [100, 101, 102]);
    const r = computePriceReaction('^GSPC', '2026-03-03T00:00:00Z', s);
    expect(r.availability).toBe('UNAVAILABLE');
    expect(r.measures).toHaveLength(0);
    expect(r.note).toMatch(/history starts later/i);
  });

  it('handles an event more recent than the last close', () => {
    const s = series('2026-03-01', [100, 101, 102]);
    const r = computePriceReaction('^GSPC', '2026-03-10T00:00:00Z', s);
    // Baseline is the last close before the event; no post-event days.
    expect(r.baseline?.date).toBe('2026-03-03');
    expect(r.measures).toHaveLength(0);
    expect(r.daysAfter).toBe(0);
    expect(r.note).toMatch(/not yet measurable/i);
  });

  it('caps a window at the available history instead of inventing a close', () => {
    // Only 2 post-event sessions exist, so +5 and +20 must reuse the last close.
    const s = series('2026-03-01', [100, 100, 100, 105, 106]);
    const r = computePriceReaction('^GSPC', '2026-03-03T00:00:00Z', s);
    const five = r.measures.find((m) => m.window === 5);
    expect(five?.to).toBe('2026-03-05');
    expect(r.daysAfter).toBe(2);
    expect(r.measures).toHaveLength(REACTION_WINDOWS.length);
  });

  it('never divides by zero and never emits NaN', () => {
    const s = series('2026-03-01', [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    const r = computePriceReaction('X', '2026-03-03T00:00:00Z', s);
    for (const m of r.measures) expect(Number.isFinite(m.changePct)).toBe(true);
  });

  it('ignores malformed points and empty input', () => {
    expect(computePriceReaction('X', '2026-03-03T00:00:00Z', []).availability).toBe('UNAVAILABLE');
    const junk = [{ date: '', value: Number.NaN }, { date: '2026-03-01', value: 5 }] as PricePoint[];
    const r = computePriceReaction('X', '2026-03-01T00:00:00Z', junk);
    expect(r.baseline?.value).toBe(5);
  });
});

describe('reactionWindowLabel / daysBetween', () => {
  it('labels horizons', () => {
    expect(reactionWindowLabel(1)).toBe('+1 session');
    expect(reactionWindowLabel(20)).toBe('+20 sessions');
  });
  it('computes UTC day deltas', () => {
    expect(daysBetween('2026-03-01', '2026-03-05')).toBe(4);
  });
});
