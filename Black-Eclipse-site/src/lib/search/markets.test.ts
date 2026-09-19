import { describe, it, expect } from 'vitest';
import { resolveQuery } from './resolver';
import { marketDisplayName, MARKET_FULL_NAME, countryToMarketId } from '@/lib/markets';

describe('countryToMarketId', () => {
  it('normalizes full country names and codes to a market id', () => {
    expect(countryToMarketId('United States')).toBe('US');
    expect(countryToMarketId('US')).toBe('US');
    expect(countryToMarketId('Pakistan')).toBe('PK');
    expect(countryToMarketId('China')).toBe('CN');
    expect(countryToMarketId('United Kingdom')).toBe('UK');
  });

  it('is case-insensitive and trims, defaulting empty to US', () => {
    expect(countryToMarketId(' united states ')).toBe('US');
    expect(countryToMarketId('')).toBe('US');
    expect(countryToMarketId(null)).toBe('US');
  });

  it('passes an unknown value through upper-cased (never a wrong fallback)', () => {
    expect(countryToMarketId('Narnia')).toBe('NARNIA');
  });
});

describe('market display names', () => {
  it('returns full country names', () => {
    expect(marketDisplayName('PK')).toBe('Pakistan');
    expect(marketDisplayName('IN')).toBe('India');
    expect(marketDisplayName('US')).toBe('United States');
  });

  it('covers all screenable markets', () => {
    const codes = ['US', 'PK', 'IN', 'CN', 'TW', 'HK', 'JP', 'KR', 'SG', 'MY', 'AU', 'UK', 'DE', 'FR', 'NL', 'CA', 'BR', 'MX', 'SA', 'AE', 'ZA', 'EG', 'NG', 'RU', 'TR', 'ID', 'TH', 'VN'];
    for (const c of codes) {
      expect(MARKET_FULL_NAME[c]).toBeTruthy();
    }
  });
});

describe('market search', () => {
  it('finds a country by full name and opens the screener', () => {
    const r = resolveQuery('Pakistan');
    const market = r.items.find((i) => i.entity.id === 'market-PK');
    expect(market).toBeDefined();
    expect(market?.entity.destination.tab).toBe('discovery');
    expect(market?.entity.destination.params?.market).toBe('PK');
  });

  it('finds a country by code', () => {
    const r = resolveQuery('IN');
    const market = r.items.find((i) => i.entity.id === 'market-IN');
    expect(market).toBeDefined();
  });
});
