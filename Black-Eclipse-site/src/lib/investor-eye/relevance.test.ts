import { describe, it, expect } from 'vitest';
import { scoreRelevance, selectRelevant, KEEP_THRESHOLD } from './relevance';

function base(over: Partial<Parameters<typeof scoreRelevance>[0]> = {}) {
  return {
    countries: ['UA', 'RU'],
    isStateDyad: true,
    eventType: 'conflict' as const,
    hasEconomicSignal: false,
    ...over,
  };
}

describe('scoreRelevance', () => {
  it('scores a state-to-state military clash highly', () => {
    const r = scoreRelevance(base({ quadClass: 4, goldstein: -8, numMentions: 200 }));
    expect(r.score).toBeGreaterThanOrEqual(0.8);
    expect(r.keep).toBe(true);
    expect(r.reasons).toContain('material conflict');
    expect(r.reasons).toContain('state-to-state');
    expect(r.reasons).toContain('widely reported');
  });

  it('drops a local incident with a noise actor and no economic signal', () => {
    const r = scoreRelevance({
      actor1Type: 'SPORT',
      countries: ['US'],
      isStateDyad: false,
      eventType: 'other',
      hasEconomicSignal: false,
      numMentions: 2,
    });
    expect(r.keep).toBe(false);
    expect(r.reasons).toContain('non-market actor');
  });

  it('keeps an economic event even without conflict', () => {
    const r = scoreRelevance(base({
      eventType: 'sanction', countries: ['US', 'IR'], isStateDyad: true, hasEconomicSignal: true,
    }));
    expect(r.keep).toBe(true);
    expect(r.reasons).toContain('sanction');
  });

  it('penalises an event with no resolved geography', () => {
    const withGeo = scoreRelevance(base({ eventType: 'trade', hasEconomicSignal: true }));
    const noGeo = scoreRelevance(base({ eventType: 'trade', hasEconomicSignal: true, countries: [], isStateDyad: false }));
    expect(noGeo.score).toBeLessThan(withGeo.score);
  });

  it('does not let reach alone make noise relevant', () => {
    // A viral local story: many mentions but no state dyad, no economic signal.
    const r = scoreRelevance({
      numMentions: 500,
      countries: ['US'],
      isStateDyad: false,
      eventType: 'other',
      hasEconomicSignal: false,
    });
    expect(r.keep).toBe(false);
  });

  it('is bounded 0..1 and returns reasons', () => {
    const r = scoreRelevance(base({ quadClass: 4, goldstein: -10, numMentions: 900, hasEconomicSignal: true, actor1Type: 'MIL', actor2Type: 'GOV' }));
    expect(r.score).toBeLessThanOrEqual(1);
    expect(r.score).toBeGreaterThan(0);
    expect(r.reasons.length).toBeGreaterThan(0);
  });

  it('handles a completely empty input without throwing', () => {
    const r = scoreRelevance({ countries: [], isStateDyad: false, eventType: 'other', hasEconomicSignal: false });
    expect(r.score).toBeGreaterThanOrEqual(0);
    expect(r.keep).toBe(false);
  });
});

describe('selectRelevant', () => {
  it('filters below threshold and sorts by relevance', () => {
    const out = selectRelevant([
      { id: 'a', relevance: 0.1 },
      { id: 'b', relevance: 0.9 },
      { id: 'c', relevance: 0.5 },
    ]);
    expect(out.map((x) => x.id)).toEqual(['b', 'c']);
  });

  it('caps the output count', () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ id: `e${i}`, relevance: 0.8 }));
    expect(selectRelevant(many, 10)).toHaveLength(10);
  });

  it('uses a conservative threshold', () => {
    expect(KEEP_THRESHOLD).toBeGreaterThan(0.2);
    expect(KEEP_THRESHOLD).toBeLessThan(0.5);
  });
});
