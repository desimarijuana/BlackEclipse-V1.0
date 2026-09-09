import { describe, it, expect, beforeEach } from 'vitest';
import { resolveQuery } from './resolver';
import { getInstrumentByAlias, getPage } from './registry';

describe('registry', () => {
  it('resolves symbol aliases to the same canonical entity', () => {
    const a = getInstrumentByAlias('AAPL');
    const b = getInstrumentByAlias('apple');
    const c = getInstrumentByAlias('Apple Inc');
    expect(a?.id).toBe(b?.id);
    expect(a?.id).toBe(c?.id);
    expect(a?.destination.tab).toBe('chart');
    expect(a?.destination.params?.symbol).toBe('AAPL');
  });

  it('resolves crypto aliases', () => {
    const btc = getInstrumentByAlias('BTC');
    expect(btc?.destination.params?.symbol).toBe('BTC');
    const btcusd = getInstrumentByAlias('BTCUSD');
    expect(btcusd?.id).toBe(btc?.id);
  });

  it('resolves indicator keywords', () => {
    const nfp = getInstrumentByAlias('us jobs data');
    expect(nfp?.symbol).toBe('NFP');
    expect(nfp?.destination.subroute).toBe('economics.calendar');
  });

  it('looks up pages by id', () => {
    const portfolio = getPage('page-portfolio');
    expect(portfolio?.destination.tab).toBe('portfolio');
  });

  it('returns undefined for unknown symbols', () => {
    expect(getInstrumentByAlias('ZZZZZZ')).toBeUndefined();
  });

  it('resolves forex, commodity and index instruments', () => {
    expect(getInstrumentByAlias('EURUSD')?.assetClass).toBe('forex');
    expect(getInstrumentByAlias('gold')?.assetClass).toBe('commodity');
    expect(getInstrumentByAlias('S&P 500')?.assetClass).toBe('index');
    expect(getInstrumentByAlias('crude oil')?.symbol).toBe('CL');
  });
});

describe('resolveQuery', () => {
  beforeEach(() => {
    // Ensure no universe cache from a previous test run interferes.
    if (typeof window !== 'undefined') sessionStorage.removeItem('black-eclipse:universe-index');
  });

  it('ranks exact symbol match first for AAPL', () => {
    const results = resolveQuery('AAPL');
    expect(results.items[0]).toBeDefined();
    expect(results.items[0].entity.symbol).toBe('AAPL');
    expect(results.items[0].match).toBe('exact');
  });

  it('resolves crypto and indicators deterministically', () => {
    const btc = resolveQuery('BTC').items[0];
    expect(btc.entity.symbol).toBe('BTC');
    const nfp = resolveQuery('NFP').items[0];
    expect(nfp.entity.symbol).toBe('NFP');
  });

  it('finds pages by fuzzy name', () => {
    const res = resolveQuery('portfoli');
    expect(res.items.some((r) => r.entity.destination.tab === 'portfolio')).toBe(true);
  });

  it('fuzzy matches misspellings in static registry', () => {
    const res = resolveQuery('Aplle');
    expect(res.items.some((r) => r.entity.symbol === 'AAPL')).toBe(true);
  });

  it('returns nothing for empty query', () => {
    expect(resolveQuery('').items).toEqual([]);
  });
});
