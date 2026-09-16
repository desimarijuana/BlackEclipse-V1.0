import { describe, it, expect } from 'vitest';
import { resolveEventLocation, reResolveEventLocation, GEO_METHOD_LABEL, GEO_METHOD_RANK } from './geo-resolve';
import { capitalByIso2, CAPITALS, countryByIso2 } from './countries';
import type { NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'Some event',
    eventType: 'monetary',
    severity: 'medium',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['US'],
    confidence: 0.5,
    sourceCount: 1,
    sources: [],
    primarySource: 'news',
    publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

describe('CAPITALS', () => {
  it('is well-formed and covers the majors', () => {
    expect(CAPITALS.length).toBeGreaterThan(70);
    for (const c of CAPITALS) {
      expect(c.iso2).toMatch(/^[A-Z]{2}$/);
      expect(c.lon).toBeGreaterThanOrEqual(-180);
      expect(c.lon).toBeLessThanOrEqual(180);
      expect(c.lat).toBeGreaterThanOrEqual(-90);
      expect(c.lat).toBeLessThanOrEqual(90);
    }
  });

  it('every capital maps to a real country', () => {
    for (const c of CAPITALS) {
      expect(countryByIso2(c.iso2), `${c.name} → ${c.iso2}`).toBeDefined();
    }
  });

  it('is NOT the country centroid (that is the whole point)', () => {
    const us = countryByIso2('US')!;
    const dc = capitalByIso2('US')!;
    // The US centroid is in Kansas; the capital is over 1,500 km away.
    expect(Math.abs(dc.lon - us.lon)).toBeGreaterThan(20);
    const br = countryByIso2('BR')!;
    const brasilia = capitalByIso2('BR')!;
    // Brasília sits ~180 km from the Brazilian centroid — still a real move
    // (~1.6° latitude), just less dramatic than the US case.
    expect(Math.abs(brasilia.lat - br.lat)).toBeGreaterThan(1);
    expect(Math.abs(brasilia.lon - br.lon)).toBeGreaterThan(3);
  });

  it('returns undefined for unknown input', () => {
    expect(capitalByIso2('ZZ')).toBeUndefined();
    expect(capitalByIso2(null)).toBeUndefined();
  });
});

describe('resolveEventLocation', () => {
  it('prefers a named place over the capital', () => {
    const us = countryByIso2('US')!;
    const r = resolveEventLocation('Strike at the Port of Houston', 'shipping', ['US'], us);
    expect(r.geoMethod).toBe('place');
    expect(r.placeName).toBe('Houston');
  });

  it('uses the CAPITAL for a policy event instead of the country centre', () => {
    const us = countryByIso2('US')!;
    const r = resolveEventLocation('Fed raises rates again', 'monetary', ['US'], us);
    expect(r.geoMethod).toBe('capital');
    expect(r.placeName).toBe('Washington, D.C.');
    // Must not be the Kansas centroid.
    expect(r.lat).toBeCloseTo(38.91, 1);
  });

  it('uses the capital for fiscal, regulatory, diplomatic and election events', () => {
    const br = countryByIso2('BR')!;
    for (const type of ['fiscal', 'regulatory', 'diplomatic', 'election', 'sanction', 'trade'] as const) {
      const r = resolveEventLocation('Generic policy statement', type, ['BR'], br);
      expect(r.geoMethod, type).toBe('capital');
      expect(r.placeName, type).toBe('Brasília');
    }
  });

  it('does NOT force a physical event to the capital', () => {
    const us = countryByIso2('US')!;
    for (const type of ['conflict', 'military', 'natural_disaster', 'energy', 'shipping'] as const) {
      const r = resolveEventLocation('Nothing geographically specific', type, ['US'], us);
      // Falls through to the country centroid, not the capital.
      expect(r.geoMethod, type).toBe('centroid');
    }
  });

  it('falls back to the centroid when no capital is known', () => {
    const unknown = { iso2: 'ZZ', iso3: 'ZZZ', name: 'Nowhere', region: 'X', lon: 10, lat: 20 };
    const r = resolveEventLocation('policy statement', 'monetary', ['ZZ'], unknown);
    expect(r.geoMethod).toBe('centroid');
    expect(r.lon).toBe(10);
  });

  it('returns nothing when there is no country and no place', () => {
    const r = resolveEventLocation('vague text', 'monetary', [], undefined);
    expect(r.lon).toBeUndefined();
    expect(r.geoMethod).toBeUndefined();
  });
});

describe('reResolveEventLocation', () => {
  it('never second-guesses an exact provider coordinate', () => {
    const e = event({ geoMethod: 'provider', lat: 12.34, lon: 56.78, eventType: 'monetary' });
    const r = reResolveEventLocation(e);
    expect(r.geoMethod).toBe('provider');
    expect(r.lat).toBe(12.34);
  });

  it('upgrades a stored centroid policy event to its capital', () => {
    const us = countryByIso2('US')!;
    // A row persisted before capitals existed: centroid + stale geoMethod.
    const e = event({ geoMethod: 'centroid', lat: us.lat, lon: us.lon, title: 'Fed holds rates steady' });
    const r = reResolveEventLocation(e);
    expect(r.geoMethod).toBe('capital');
    expect(r.placeName).toBe('Washington, D.C.');
  });

  it('keeps a previously-resolved place', () => {
    const e = event({ geoMethod: 'place', lat: 29.76, lon: -95.37, placeName: 'Houston' });
    const r = reResolveEventLocation(e);
    expect(r.geoMethod).toBe('place');
    expect(r.lat).toBe(29.76);
  });

  it('does not downgrade an event to no-location', () => {
    const e = event({ geoMethod: 'centroid', lat: 5, lon: 5, countries: [] });
    const r = reResolveEventLocation(e);
    expect(r.lon).toBe(5);
    expect(r.lat).toBe(5);
  });
});

describe('labels and ranking', () => {
  it('labels every method so precision is never overstated', () => {
    for (const m of ['provider', 'place', 'capital', 'centroid'] as const) {
      expect(GEO_METHOD_LABEL[m].length).toBeGreaterThan(0);
      expect(GEO_METHOD_RANK[m]).toBeGreaterThan(0);
    }
    expect(GEO_METHOD_RANK.provider).toBeGreaterThan(GEO_METHOD_RANK.capital);
    expect(GEO_METHOD_RANK.capital).toBeGreaterThan(GEO_METHOD_RANK.centroid);
  });
});
