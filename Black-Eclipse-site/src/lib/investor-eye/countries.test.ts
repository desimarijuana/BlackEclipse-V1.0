import { describe, it, expect } from 'vitest';
import {
  resolveCountry, countryByIso2, extractCountries, nearestCountry, resolveMapFeatureName, COUNTRIES,
} from './countries';

describe('countryByIso2', () => {
  it('resolves known codes case-insensitively', () => {
    expect(countryByIso2('us')?.name).toBe('United States');
    expect(countryByIso2('PK')?.name).toBe('Pakistan');
    expect(countryByIso2('tw')?.marketId).toBe('TW');
  });

  it('returns undefined for unknown input', () => {
    expect(countryByIso2('ZZ')).toBeUndefined();
    expect(countryByIso2(null)).toBeUndefined();
  });
});

describe('resolveCountry', () => {
  it('resolves names and aliases', () => {
    expect(resolveCountry('Pakistan')?.iso2).toBe('PK');
    expect(resolveCountry('USA')?.iso2).toBe('US');
    expect(resolveCountry('britain')?.iso2).toBe('GB');
    expect(resolveCountry('Riyadh')?.iso2).toBe('SA');
  });

  it('handles possessives and embedded mentions', () => {
    expect(resolveCountry("Pakistan's economy")?.iso2).toBe('PK');
  });

  it('returns undefined for non-countries', () => {
    expect(resolveCountry('atlantis')).toBeUndefined();
  });
});

describe('extractCountries', () => {
  it('extracts multiple countries from text', () => {
    const found = extractCountries('US and China trade talks with Germany').map((c) => c.iso2);
    expect(found).toContain('US');
    expect(found).toContain('CN');
    expect(found).toContain('DE');
  });

  it('does not match short noise like "in" or "or"', () => {
    const found = extractCountries('investing in ordinary shares').map((c) => c.iso2);
    expect(found).not.toContain('IN');
    expect(found).toEqual([]);
  });

  it('handles the uae/u.s. signals', () => {
    expect(extractCountries('UAE and U.S. officials meet').map((c) => c.iso2).sort()).toEqual(['AE', 'US']);
  });

  it('returns empty for empty input', () => {
    expect(extractCountries('')).toEqual([]);
    expect(extractCountries(null)).toEqual([]);
  });
});

describe('nearestCountry', () => {
  it('finds the country nearest a coordinate', () => {
    expect(nearestCountry(69.3, 30.4)?.iso2).toBe('PK');
    expect(nearestCountry(-98.5, 39.8)?.iso2).toBe('US');
    expect(nearestCountry(139.7, 35.7)?.iso2).toBe('JP');
  });

  it('returns undefined for a point far from any known centroid', () => {
    expect(nearestCountry(0, -80)).toBeUndefined();
  });
});

describe('resolveMapFeatureName', () => {
  it('matches Natural Earth admin names', () => {
    expect(resolveMapFeatureName('United States of America')?.iso2).toBe('US');
    expect(resolveMapFeatureName('South Korea')?.iso2).toBe('KR');
  });
});

describe('gazetteer integrity', () => {
  it('has unique ISO2 codes and valid centroids', () => {
    const iso2s = COUNTRIES.map((c) => c.iso2);
    expect(new Set(iso2s).size).toBe(iso2s.length);
    for (const c of COUNTRIES) {
      expect(c.lon).toBeGreaterThanOrEqual(-180);
      expect(c.lon).toBeLessThanOrEqual(180);
      expect(c.lat).toBeGreaterThanOrEqual(-90);
      expect(c.lat).toBeLessThanOrEqual(90);
    }
  });
});
