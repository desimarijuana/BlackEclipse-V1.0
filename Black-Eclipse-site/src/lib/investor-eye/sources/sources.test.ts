import { describe, it, expect } from 'vitest';
import { parseGdeltDate, normalizeArticle } from './gdelt';
import { normalizeQuake, resolveQuakeCountry } from './usgs';

describe('parseGdeltDate', () => {
  it('parses the GDELT compact timestamp', () => {
    expect(parseGdeltDate('20260915T164200Z')).toBe('2026-09-15T16:42:00.000Z');
  });

  it('returns null for malformed input', () => {
    expect(parseGdeltDate(undefined)).toBeNull();
    expect(parseGdeltDate('not-a-date')).toBeNull();
  });
});

describe('normalizeArticle', () => {
  it('builds a normalized event with classified fields and provenance', () => {
    const event = normalizeArticle(
      {
        title: 'US imposes new sanctions on Russian banks',
        seendate: '20260915T120000Z',
        url: 'https://example.com/story',
        domain: 'example.com',
      },
      'sanctions',
      '2026-09-15T12:05:00.000Z',
    );
    expect(event).not.toBeNull();
    expect(event!.eventType).toBe('sanction');
    expect(event!.countries).toContain('US');
    expect(event!.countries).toContain('RU');
    expect(event!.primarySource).toBe('gdelt');
    expect(event!.sources[0].id).toBe('example.com');
    expect(event!.dedupKey).toHaveLength(40);
    expect(event!.lon).toBeDefined();
  });

  it('returns null when there is no title', () => {
    expect(normalizeArticle({ url: 'https://x.com' }, 'x', '2026-09-15T12:00:00.000Z')).toBeNull();
  });

  it('falls back to the source country when the title names none', () => {
    const event = normalizeArticle(
      { title: 'Leaders meet for a summit', seendate: '20260915T120000Z', sourcecountry: 'France' },
      'politics',
      '2026-09-15T12:05:00.000Z',
    );
    expect(event!.countries).toContain('FR');
  });

  it('never invents a timestamp', () => {
    const retrievedAt = '2026-09-15T12:05:00.000Z';
    const event = normalizeArticle({ title: 'Something happened' }, 'x', retrievedAt);
    expect(event!.publishedAt).toBe(retrievedAt);
  });
});

describe('normalizeQuake', () => {
  it('builds a geolocated natural-disaster event with magnitude severity', () => {
    const event = normalizeQuake(
      {
        id: 'us123',
        properties: { mag: 6.4, place: '100 km S of somewhere', time: Date.parse('2026-09-15T10:00:00Z'), url: 'https://usgs.gov/q' },
        geometry: { type: 'Point', coordinates: [139.7, 35.7, 10] },
      },
      '2026-09-15T10:05:00.000Z',
    );
    expect(event).not.toBeNull();
    expect(event!.eventType).toBe('natural_disaster');
    expect(event!.severity).toBe('high');
    expect(event!.lon).toBe(139.7);
    expect(event!.lat).toBe(35.7);
    expect(event!.countries).toContain('JP');
    expect(event!.primarySource).toBe('usgs');
  });

  it('returns null when coordinates are missing', () => {
    expect(normalizeQuake({ properties: { mag: 3 } }, '2026-09-15T10:05:00.000Z')).toBeNull();
  });

  it('prefers a named country in the place text over the centroid', () => {
    expect(resolveQuakeCountry('45 km N of Ruteng, Indonesia', 120.4, -8.2)?.iso2).toBe('ID');
  });

  it('resolves a US state name to the United States (not the nearest centroid)', () => {
    // The US centroid is in Kansas, so a naive nearest-country would say MX.
    expect(resolveQuakeCountry('45 km NW of Toyah, Texas', -104.1, 31.6)?.iso2).toBe('US');
    expect(resolveQuakeCountry('Rat Islands, Aleutian Islands, Alaska', 177.9, 50.2)?.iso2).toBe('US');
  });

  it('leaves a remote ocean quake unlabelled instead of guessing', () => {
    // Empty Southern Ocean — far from every gazetteer centroid.
    expect(resolveQuakeCountry('Southern Ocean', 0, -80)).toBeUndefined();
    expect(resolveQuakeCountry('South Atlantic Ocean', -25, -55)).toBeUndefined();
  });

  it('escalates severity with magnitude', () => {
    const quake = (mag: number) =>
      normalizeQuake(
        { properties: { mag, place: 'x', time: Date.now() }, geometry: { coordinates: [0, 0] } },
        '2026-09-15T10:05:00.000Z',
      )!;
    expect(quake(7.5).severity).toBe('critical');
    expect(quake(3.0).severity).toBe('low');
  });
});
