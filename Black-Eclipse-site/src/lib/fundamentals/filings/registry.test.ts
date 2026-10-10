import { describe, it, expect } from 'vitest';
import { adapterFor, FILINGS_ADAPTERS } from './registry';
import { PROVIDER_ORDER, FUNDAMENTALS_PROVIDERS } from '../providers';
import { eclipseFilingsProvider } from '../providers/eclipse-filings';

describe('filings adapter registry', () => {
  it('serves Pakistan via the PSX adapter', () => {
    expect(adapterFor('PK')?.id).toBe('psx');
    expect(adapterFor('pk')?.id).toBe('psx');
  });

  it('returns undefined for a market with no adapter yet', () => {
    expect(adapterFor('IN')).toBeUndefined();
    expect(adapterFor('US')).toBeUndefined();
  });

  it('exposes at least one registered adapter', () => {
    expect(FILINGS_ADAPTERS.length).toBeGreaterThan(0);
  });
});

describe('eclipse-filings provider registration', () => {
  it('is in the provider order before yahoo (statement precedence)', () => {
    expect(PROVIDER_ORDER).toContain('eclipse-filings');
    expect(PROVIDER_ORDER.indexOf('eclipse-filings')).toBeLessThan(PROVIDER_ORDER.indexOf('yahoo'));
  });

  it('is keyless (always configured) and supports only its markets', () => {
    expect(FUNDAMENTALS_PROVIDERS['eclipse-filings']).toBe(eclipseFilingsProvider);
    expect(eclipseFilingsProvider.isConfigured()).toBe(true);
    expect(eclipseFilingsProvider.supports('OGDC', 'PK')).toBe(true);
    expect(eclipseFilingsProvider.supports('AAPL', 'US')).toBe(false);
  });
});
