import { describe, it, expect } from 'vitest';
import { buildSituations, situationForEvent, situationsProvenance } from './situations';
import type { NormalizedEvent, EventSeverity } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'Event',
    eventType: 'conflict',
    severity: 'medium',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['IR'],
    confidence: 0.5,
    sourceCount: 1,
    sources: [],
    primarySource: 'gdelt',
    publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

/** Build n events of one type/place, one day apart, with given severities. */
function run(severities: EventSeverity[], place = 'Strait of Hormuz'): NormalizedEvent[] {
  return severities.map((severity, i) =>
    event({
      id: `e${i}`,
      dedupKey: `k${i}`,
      severity,
      placeName: place,
      publishedAt: new Date(Date.parse('2026-09-10T00:00:00Z') + i * 86400000).toISOString(),
    }),
  );
}

describe('buildSituations', () => {
  it('groups same type + country and counts them', () => {
    const s = buildSituations(run(['medium', 'high', 'critical']));
    expect(s).toHaveLength(1);
    expect(s[0].count).toBe(3);
    // The label is the COUNTRY: the count is country-wide.
    expect(s[0].area).toBe('Iran');
    // The place the sources agree on is offered separately, as context.
    expect(s[0].topPlace).toBe('Strait of Hormuz');
    expect(s[0].maxSeverity).toBe('critical');
  });

  it('omits single-occurrence situations by default (no recurrence to report)', () => {
    expect(buildSituations(run(['high']))).toHaveLength(0);
    // ...but can include them when asked.
    expect(buildSituations(run(['high']), 1)).toHaveLength(1);
  });

  // Regression: bucketing by raw place string fragmented ONE situation into
  // several ("US", "United States", "Washington", "Washington, D.C."), because
  // providers disagree on granularity. Bucket by country instead.
  it('buckets by country, so differing place granularity does not fragment it', () => {
    const varying = [
      event({ id: 'a', dedupKey: 'a', countries: ['US'], placeName: 'Washington, D.C.' }),
      event({ id: 'b', dedupKey: 'b', countries: ['US'], placeName: 'Washington' }),
      event({ id: 'c', dedupKey: 'c', countries: ['US'], placeName: undefined }),
    ];
    const s = buildSituations(varying);
    expect(s).toHaveLength(1);
    expect(s[0].count).toBe(3);
    expect(s[0].area).toBe('United States');
    expect(s[0].distinctPlaces).toBe(2);
  });

  // A country-wide count must never be labelled with one city, which would imply
  // all the incidents happened there.
  it('does not label a country-wide count with a single place', () => {
    const s = buildSituations([
      event({ id: 'a', dedupKey: 'a', countries: ['US'], placeName: 'Sudbury' }),
      event({ id: 'b', dedupKey: 'b', countries: ['US'], placeName: 'Houston' }),
    ]);
    expect(s[0].area).toBe('United States');
    expect(s[0].distinctPlaces).toBe(2);
  });

  it('reports one distinct place when the incidents really are concentrated', () => {
    const s = buildSituations(run(['high', 'high']));
    expect(s[0].distinctPlaces).toBe(1);
    expect(s[0].topPlace).toBe('Strait of Hormuz');
  });

  it('falls back to the country code when the country is unknown', () => {
    const events = [
      event({ id: 'a', dedupKey: 'a', countries: ['ZZ'], placeName: undefined }),
      event({ id: 'b', dedupKey: 'b', countries: ['ZZ'], placeName: undefined }),
    ];
    expect(buildSituations(events)[0].area).toBe('ZZ');
  });

  it('keeps different event types apart even in the same country', () => {
    const events = [
      event({ id: 'a', dedupKey: 'a', eventType: 'conflict', countries: ['IR'] }),
      event({ id: 'b', dedupKey: 'b', eventType: 'shipping', countries: ['IR'] }),
    ];
    expect(buildSituations(events, 1)).toHaveLength(2);
  });

  it('keeps different countries apart', () => {
    const events = [
      event({ id: 'a', dedupKey: 'a', countries: ['IR'] }),
      event({ id: 'b', dedupKey: 'b', countries: ['TW'] }),
    ];
    expect(buildSituations(events, 1)).toHaveLength(2);
  });

  it('computes the span and orders occurrences chronologically', () => {
    const s = buildSituations(run(['low', 'medium', 'high']));
    expect(s[0].spanHours).toBe(48);
    const times = s[0].occurrences.map((o) => o.publishedAt);
    expect([...times].sort()).toEqual(times);
  });

  it('reports escalating only for a real rising trend of 3+ points', () => {
    expect(buildSituations(run(['low', 'medium', 'high']))[0].escalating).toBe(true);
    // Two points is a comparison, not a trend.
    expect(buildSituations(run(['low', 'critical']))[0].escalating).toBe(false);
    // Three points but falling.
    expect(buildSituations(run(['critical', 'high', 'low']))[0].escalating).toBe(false);
    // Flat.
    expect(buildSituations(run(['high', 'high', 'high']))[0].escalating).toBe(false);
  });

  it('exposes the severity trend in order', () => {
    const s = buildSituations(run(['low', 'high']), 1)[0];
    expect(s.severityTrend).toEqual([0.2, 0.75]);
  });

  it('ignores events with no country at all', () => {
    const orphan = event({ countries: [], placeName: undefined });
    expect(buildSituations([orphan, orphan], 1)).toHaveLength(0);
  });

  it('sorts by recurrence, then severity, then recency', () => {
    const many = run(['medium', 'medium', 'medium'], 'Hormuz');
    const severe = run(['critical', 'critical'], 'Taiwan Strait').map((e) => ({ ...e, countries: ['TW'] }));
    const s = buildSituations([...many, ...severe]);
    expect(s[0].count).toBe(3);
    expect(s[1].count).toBe(2);
    expect(s[1].maxSeverity).toBe('critical');
  });
});

describe('situationForEvent', () => {
  it('finds the situation an event belongs to', () => {
    const events = run(['low', 'high', 'critical']);
    const s = situationForEvent(events[1], events);
    expect(s?.count).toBe(3);
    expect(s?.area).toBe('Iran');
    expect(s?.topPlace).toBe('Strait of Hormuz');
  });

  it('returns undefined for an event with no anchor', () => {
    const orphan = event({ countries: [], placeName: undefined });
    expect(situationForEvent(orphan, [orphan])).toBeUndefined();
  });
});

describe('situationsProvenance', () => {
  it('is UNAVAILABLE for an empty window', () => {
    expect(situationsProvenance([])).toBe('UNAVAILABLE');
    expect(situationsProvenance([event()])).toBe('LIVE');
  });
});
