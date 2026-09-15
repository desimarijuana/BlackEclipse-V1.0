import { describe, it, expect } from 'vitest';
import {
  buildRiskState, computeExposure, portfolioIntersections, buildTransmissions,
  buildAnalogues, buildRegionState, planQuery, scoreEventAgainstPlan, buildGlobalState,
} from './analytics';
import type { CountrySummary, MarketObservation, NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    dedupKey: Math.random().toString(36),
    title: 'Event',
    eventType: 'trade',
    severity: 'medium',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['US'],
    confidence: 0.5,
    sourceCount: 1,
    sources: [],
    primarySource: 'gdelt',
    publishedAt: '2026-09-15T10:00:00.000Z',
    ...overrides,
  };
}

const countries: CountrySummary[] = [
  { iso2: 'US', name: 'United States', region: 'North America', lon: -98.5, lat: 39.8, eventCount: 3, markets: [] },
  { iso2: 'CN', name: 'China', region: 'East Asia', lon: 104.2, lat: 35.9, eventCount: 2, markets: [] },
];

const markets: MarketObservation[] = [
  { marketId: 'US', iso2: 'US', name: 'United States', symbol: 'S&P 500', price: 5000, changePct: 0.7, provenance: 'LIVE' },
  { marketId: 'CN', iso2: 'CN', name: 'China', symbol: 'Shanghai Composite', price: 3200, changePct: -0.5, provenance: 'LIVE' },
];

describe('buildRiskState', () => {
  it('produces one component per dimension with drivers and sample size', () => {
    const components = buildRiskState([
      event({ eventType: 'conflict', severity: 'high', countries: ['UA'] }),
      event({ eventType: 'trade', countries: ['CN'] }),
    ]);
    expect(components).toHaveLength(7);
    for (const c of components) {
      expect(c.score).toBeGreaterThanOrEqual(0);
      expect(c.score).toBeLessThanOrEqual(1);
      expect(Array.isArray(c.drivers)).toBe(true);
      expect(typeof c.sampleSize).toBe('number');
    }
    const conflict = components.find((c) => c.id === 'conflict')!;
    expect(conflict.sampleSize).toBe(1);
    expect(conflict.drivers.join(' ')).toContain('UA');
  });

  it('is zero with no events', () => {
    for (const c of buildRiskState([])) expect(c.score).toBe(0);
  });
});

describe('computeExposure', () => {
  it('aggregates country and sector weights', () => {
    const exposure = computeExposure([
      { symbol: 'A', weight: 0.5, country: 'US', sector: 'Technology' },
      { symbol: 'B', weight: 0.3, country: 'TW', sector: 'Technology' },
      { symbol: 'C', weight: 0.2, country: 'US', sector: 'Energy' },
    ]);
    expect(exposure.countries.find((c) => c.key === 'US')?.weight).toBeCloseTo(0.7);
    expect(exposure.sectors.find((s) => s.key === 'Technology')?.weight).toBeCloseTo(0.8);
    expect(exposure.total).toBeCloseTo(1);
  });

  it('tracks unmapped weight instead of guessing', () => {
    const exposure = computeExposure([{ symbol: 'X', weight: 0.4 }]);
    expect(exposure.unmappedWeight).toBeCloseTo(0.4);
    expect(exposure.countries).toEqual([]);
  });
});

describe('portfolioIntersections', () => {
  it('finds events intersecting held countries/sectors and marks OBSERVED', () => {
    const exposure = computeExposure([
      { symbol: 'A', weight: 0.6, country: 'TW', sector: 'Technology' },
    ]);
    const intersections = portfolioIntersections(
      [event({ countries: ['TW'], sectors: ['Technology'] }), event({ countries: ['BR'] })],
      exposure,
    );
    expect(intersections).toHaveLength(1);
    expect(intersections[0].relation).toBe('OBSERVED');
    expect(intersections[0].matchedCountries).toEqual(['TW']);
  });

  it('returns nothing when there is no overlap', () => {
    const exposure = computeExposure([{ symbol: 'A', weight: 1, country: 'JP' }]);
    expect(portfolioIntersections([event({ countries: ['BR'] })], exposure)).toEqual([]);
  });
});

describe('buildTransmissions', () => {
  it('chains event → country → channel → asset and labels inference', () => {
    const transmissions = buildTransmissions(
      [event({ eventType: 'energy', channels: ['Energy'], countries: ['US'], id: 'e1' })],
      markets,
    );
    expect(transmissions).toHaveLength(1);
    const kinds = transmissions[0].steps.map((s) => s.kind);
    expect(kinds[0]).toBe('event');
    expect(kinds).toContain('channel');
    expect(kinds).toContain('asset');
    expect(transmissions[0].relation).toBe('INFERRED');
    expect(transmissions[0].steps.find((s) => s.kind === 'country')?.relation).toBe('OBSERVED');
  });

  it('handles events with no channels', () => {
    const transmissions = buildTransmissions([event({ channels: [] })], markets);
    expect(transmissions[0].steps.length).toBeGreaterThanOrEqual(1);
  });
});

describe('buildAnalogues', () => {
  it('summarises prior periods and real series availability', () => {
    const target = event({ eventType: 'trade' });
    const prior = [
      event({ eventType: 'trade', publishedAt: '2024-05-01T00:00:00.000Z' }),
      event({ eventType: 'trade', publishedAt: '2024-06-01T00:00:00.000Z' }),
      event({ eventType: 'trade', publishedAt: '2022-03-01T00:00:00.000Z' }),
    ];
    const analogues = buildAnalogues(target, prior, [
      { date: '2022-01-01', value: 100 },
      { date: '2024-12-31', value: 120 },
    ], 'SPX');
    expect(analogues.sampleSize).toBe(3);
    expect(analogues.analoguePeriods.find((p) => p.label === '2024')?.eventCount).toBe(2);
    expect(analogues.availability).toBe('HISTORICAL');
    expect(analogues.dateRange).toEqual({ from: '2022-01-01', to: '2024-12-31' });
    expect(analogues.disclaimer.toLowerCase()).toContain('not predictive');
  });

  it('marks unavailable when there is no series', () => {
    const analogues = buildAnalogues(event(), []);
    expect(analogues.availability).toBe('UNAVAILABLE');
    expect(analogues.dateRange).toBeNull();
  });
});

describe('buildRegionState', () => {
  it('aggregates events by region', () => {
    const regions = buildRegionState(
      [event({ countries: ['US'] }), event({ countries: ['CN'] })],
      countries,
    );
    expect(regions.find((r) => r.region === 'North America')?.eventCount).toBe(1);
    expect(regions.find((r) => r.region === 'East Asia')?.eventCount).toBe(1);
  });
});

describe('planQuery', () => {
  it('activates energy/trade/conflict layers from keywords', () => {
    expect(planQuery('What is affecting oil?').activateLayers).toContain('energy');
    expect(planQuery('Show trade flows involving China').activateLayers).toContain('trade');
    expect(planQuery('show taiwan semiconductor risk').activateLayers).toContain('companies');
  });

  it('extracts countries and event types', () => {
    const plan = planQuery('Show Taiwan semiconductor risk');
    expect(plan.countries).toContain('TW');
    expect(plan.explanation.length).toBeGreaterThan(0);
  });

  it('always includes the base events layer', () => {
    expect(planQuery('hello').activateLayers).toContain('events');
  });
});

describe('scoreEventAgainstPlan', () => {
  it('ranks matching events above unrelated ones', () => {
    const plan = planQuery('oil energy');
    const match = event({ eventType: 'energy', commodities: ['Crude Oil'] });
    const other = event({ eventType: 'election', commodities: [] });
    expect(scoreEventAgainstPlan(match, plan)).toBeGreaterThan(scoreEventAgainstPlan(other, plan));
  });

  it('gives zero to an event that matches nothing, regardless of severity', () => {
    const plan = planQuery('oil energy');
    const unrelated = event({ eventType: 'election', severity: 'critical', commodities: [], countries: ['BR'] });
    expect(scoreEventAgainstPlan(unrelated, plan)).toBe(0);
  });
});

describe('buildGlobalState', () => {
  it('assembles the documented state object', () => {
    const state = buildGlobalState([event()], countries, markets, 'LIVE', 24);
    expect(state.regions.length).toBeGreaterThan(0);
    expect(state.countries).toBe(countries);
    expect(state.marketState).toBe(markets);
    expect(state.riskState).toHaveLength(7);
    expect(state.provenance).toBe('LIVE');
  });
});
