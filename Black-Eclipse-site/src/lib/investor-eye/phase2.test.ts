import { describe, it, expect } from 'vitest';
import { ECONOMIC_METRICS } from './phase2';

// The FRED series map is module-private, but the transform decision is the
// bug-prone part. These assertions pin the public metric catalog and the
// documented rule: a series' yoy-ness is a property of the series, never of
// the metric (so `CPALTT01*` series must NOT be re-transformed).
describe('ECONOMIC_METRICS', () => {
  it('exposes a stable, non-empty metric catalog with unique ids', () => {
    expect(ECONOMIC_METRICS.length).toBeGreaterThan(0);
    const ids = ECONOMIC_METRICS.map((m) => m.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('gives every metric a label, unit and FRED id', () => {
    for (const m of ECONOMIC_METRICS) {
      expect(m.label.length).toBeGreaterThan(0);
      expect(typeof m.unit).toBe('string');
      expect(m.fredId.length).toBeGreaterThan(0);
    }
  });

  it('only marks index series (not already-YoY series) for yoy transform', () => {
    const byId = new Map(ECONOMIC_METRICS.map((m) => [m.id, m]));
    expect(byId.get('inflation')?.fredId).toBe('CPIAUCSL');
    expect(byId.get('unemployment')?.transform).toBeUndefined();
    expect(byId.get('rate')?.transform).toBeUndefined();
  });
});
