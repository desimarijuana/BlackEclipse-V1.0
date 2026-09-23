import { describe, it, expect } from 'vitest';
import {
  APP_TABS,
  destinationToHref,
  destinationToQuery,
  hrefForTab,
  parseDeepLink,
} from './deep-link';

describe('destinationToQuery / href', () => {
  it('serializes a plain tab', () => {
    expect(destinationToQuery({ tab: 'portfolio' })).toBe('tab=portfolio');
    expect(destinationToHref({ tab: 'portfolio' })).toBe('/?tab=portfolio');
  });

  it('includes a subroute and params', () => {
    const href = destinationToHref({
      tab: 'economics',
      subroute: 'economics.calendar',
      params: { focus: 'NFP' },
    });
    expect(href).toBe('/?tab=economics&sub=economics.calendar&focus=NFP');
  });

  it('drops empty param values', () => {
    expect(destinationToQuery({ tab: 'chart', params: { symbol: 'AAPL', market: '' } }))
      .toBe('tab=chart&symbol=AAPL');
  });

  it('hrefForTab builds a tab link with optional params', () => {
    expect(hrefForTab('chart', { symbol: 'AAPL' })).toBe('/?tab=chart&symbol=AAPL');
  });
});

describe('parseDeepLink', () => {
  it('parses a tab with params', () => {
    expect(parseDeepLink('?tab=chart&symbol=AAPL')).toEqual({
      tab: 'chart',
      params: { symbol: 'AAPL' },
    });
  });

  it('parses a tab with a subroute', () => {
    expect(parseDeepLink('?tab=economics&sub=economics.calendar&focus=NFP')).toEqual({
      tab: 'economics',
      subroute: 'economics.calendar',
      params: { focus: 'NFP' },
    });
  });

  it('accepts a search string without the leading ?', () => {
    expect(parseDeepLink('tab=portfolio')?.tab).toBe('portfolio');
  });

  it('recognizes every tab', () => {
    for (const tab of APP_TABS) {
      expect(parseDeepLink(`?tab=${tab}`)?.tab).toBe(tab);
    }
  });

  it('falls back to the chart tab for a bare symbol (back-compat)', () => {
    expect(parseDeepLink('?symbol=AAPL')).toEqual({ tab: 'chart', params: { symbol: 'AAPL' } });
  });

  it('returns null for an unknown tab or empty input', () => {
    expect(parseDeepLink('?tab=nope')).toBeNull();
    expect(parseDeepLink('')).toBeNull();
    expect(parseDeepLink('?')).toBeNull();
  });

  it('round-trips through destinationToQuery', () => {
    const dest = { tab: 'discovery' as const, params: { symbol: 'MSFT', focus: 'chart' } };
    expect(parseDeepLink(`?${destinationToQuery(dest)}`)).toEqual(dest);
  });
});
