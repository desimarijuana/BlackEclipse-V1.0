import { describe, it, expect } from 'vitest';
import { inflateRawSync } from 'node:zlib';
import { parseLastUpdate, normalizeExportRow, inflateZipEntry } from './gdelt';
import { normalizeQuake, resolveQuakeCountry } from './usgs';

describe('parseLastUpdate', () => {
  const body = [
    '120506 18e18fecbbc5d43bd5e77993f20d9f1e http://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip',
    '155776 78a951719270ab27c4b92a04cbe83e45 http://data.gdeltproject.org/gdeltv2/20260916151500.mentions.CSV.zip',
    '7455364 19a88cbb8ab79b72d9c5a2c1fbd05772 http://data.gdeltproject.org/gdeltv2/20260916151500.gkg.csv.zip',
  ].join('\n');

  it('prefers the event export URL and upgrades it to https', () => {
    // GDELT advertises http:// URLs; the transport is https-only, so the scheme
    // must be upgraded rather than weakening safeGet. Its host serves TLS.
    expect(parseLastUpdate(body)).toBe(
      'https://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip',
    );
  });

  it('returns null when the body has no URL', () => {
    expect(parseLastUpdate('')).toBeNull();
    expect(parseLastUpdate('garbage')).toBeNull();
  });
});

describe('inflateZipEntry', () => {
  it('rejects a non-zip buffer clearly', () => {
    expect(() => inflateZipEntry(Buffer.from('not a zip at all'), inflateRawSync)).toThrow(/zip/i);
  });
});

describe('normalizeExportRow', () => {
  // A 61-column GDELT 2.0 export row, built from the real field layout.
  const row = (over: Record<number, string> = {}) => {
    const f = new Array(61).fill('');
    f[0] = '1234567890';
    f[3] = '2026';
    f[6] = 'UNITED STATES';
    f[7] = 'USA';
    f[16] = 'RUSSIA';
    f[17] = 'RUS';
    f[25] = '1';
    f[26] = '172';
    f[28] = '17';
    f[29] = '4';
    f[30] = '-9.0';
    f[31] = '150';
    f[32] = '42';
    f[33] = '60';
    f[34] = '-4.2';
    f[52] = 'Moscow, Moscow, Russia';
    f[53] = 'RS';
    f[56] = '55.75';
    f[57] = '37.61';
    f[59] = '20260916151500';
    f[60] = 'https://example.com/story';
    for (const [i, v] of Object.entries(over)) f[Number(i)] = v;
    return f;
  };

  it('decodes a CAMEO coercion event as a sanction with dyad countries', () => {
    const event = normalizeExportRow(row(), '2026-09-16T15:20:00.000Z');
    expect(event).not.toBeNull();
    expect(event!.eventType).toBe('sanction'); // root 17 = coerce
    expect(event!.severity).toBe('critical');  // goldstein -9
    expect(event!.countries).toContain('RU');   // action geo (FIPS RS -> RU)
    expect(event!.countries).toContain('US');   // actor 1
    expect(event!.lon).toBe(37.61);
    expect(event!.lat).toBe(55.75);
    expect(event!.primarySource).toBe('gdelt');
    expect(event!.sourceCount).toBe(42); // NumSources corroboration
    expect(event!.dedupKey).toHaveLength(40);
  });

  it('classifies material conflict (quad 4) as conflict', () => {
    const event = normalizeExportRow(row({ 26: '190', 28: '19', 29: '4' }), '2026-09-16T15:20:00.000Z')!;
    expect(event.eventType).toBe('conflict');
  });

  it('maps cooperative codes without downgrading material conflict', () => {
    // Root 04 (consult) with hostile goldstein still reads as diplomatic type,
    // but severity reflects the real Goldstein value.
    const event = normalizeExportRow(row({ 26: '040', 28: '04', 29: '1', 30: '-6.0' }), '2026-09-16T15:20:00.000Z')!;
    expect(event.eventType).toBe('diplomatic');
    expect(event.severity).toBe('high');
  });

  it('returns null without an id or event code', () => {
    expect(normalizeExportRow(row({ 0: '' }), '2026-09-16T15:20:00.000Z')).toBeNull();
    expect(normalizeExportRow(row({ 26: '' }), '2026-09-16T15:20:00.000Z')).toBeNull();
  });

  it('omits coordinates when the action geo is 0/0 (unknown)', () => {
    const event = normalizeExportRow(row({ 56: '0', 57: '0' }), '2026-09-16T15:20:00.000Z')!;
    expect(event.lon).toBeUndefined();
    expect(event.lat).toBeUndefined();
  });

  it('never invents a timestamp when DATEADDED is malformed', () => {
    const retrievedAt = '2026-09-16T15:20:00.000Z';
    const event = normalizeExportRow(row({ 59: 'nonsense' }), retrievedAt)!;
    expect(event.publishedAt).toBe(retrievedAt);
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
