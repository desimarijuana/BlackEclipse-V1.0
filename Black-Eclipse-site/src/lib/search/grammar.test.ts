import { describe, it, expect } from 'vitest';
import { matchesFilters, parseQuery, scopeKinds, SCOPES, type Scope } from './grammar';

describe('parseQuery', () => {
  it('defaults to the all scope with the raw text', () => {
    const p = parseQuery('aapl price');
    expect(p.scope).toBe('all');
    expect(p.text).toBe('aapl price');
    expect(p.filters).toEqual({});
    expect(p.showHelp).toBe(false);
  });

  it('detects each scope prefix and strips it', () => {
    const cases: [string, Scope, string][] = [
      ['> open portfolio', 'action', 'open portfolio'],
      ['# BTC', 'symbol', 'BTC'],
      ['@ cpi', 'indicator', 'cpi'],
      ['/ portfolio', 'page', 'portfolio'],
      ['~ my fund', 'user', 'my fund'],
    ];
    for (const [raw, scope, text] of cases) {
      const p = parseQuery(raw);
      expect(p.scope).toBe(scope);
      expect(p.text).toBe(text);
    }
    expect(SCOPES).toHaveLength(6);
  });

  it('treats a bare "?" as a help request', () => {
    expect(parseQuery('?').showHelp).toBe(true);
    expect(parseQuery('?').text).toBe('');
    expect(parseQuery('? ').showHelp).toBe(true);
    expect(parseQuery('? nfp').showHelp).toBe(false);
    expect(parseQuery('? nfp').text).toBe('nfp');
  });

  it('extracts field operators and leaves plain terms', () => {
    const p = parseQuery('kind:crypto btc');
    expect(p.filters).toEqual({ kind: 'crypto' });
    expect(p.text).toBe('btc');
  });

  it('supports class, market and asset (alias symbol) filters', () => {
    expect(parseQuery('class:etf sp').filters).toEqual({ class: 'etf' });
    expect(parseQuery('market:us aapl').filters).toEqual({ market: 'us' });
    expect(parseQuery('symbol:aapl').filters).toEqual({ asset: 'aapl' });
  });

  it('lowercases operator values and composes with a scope prefix', () => {
    const p = parseQuery('# class:COMMODITY gold');
    expect(p.scope).toBe('symbol');
    expect(p.filters).toEqual({ class: 'commodity' });
    expect(p.text).toBe('gold');
  });

  it('ignores unknown field prefixes', () => {
    const p = parseQuery('foo:bar aapl');
    expect(p.filters).toEqual({});
    expect(p.text).toBe('foo:bar aapl');
  });
});

describe('scopeKinds', () => {
  it('maps scopes to entity kinds', () => {
    expect(scopeKinds('all')).toBeNull();
    expect(scopeKinds('symbol')).toEqual(['security', 'instrument']);
    expect(scopeKinds('action')).toEqual(['action']);
    expect(scopeKinds('indicator')).toEqual(['indicator', 'event']);
    expect(scopeKinds('user')).toEqual(['user']);
  });
});

describe('matchesFilters', () => {
  const aapl = { kind: 'security' as const, assetClass: 'equity', market: 'US', symbol: 'AAPL' };

  it('passes when no filters', () => {
    expect(matchesFilters(aapl, {})).toBe(true);
  });

  it('filters by kind', () => {
    expect(matchesFilters(aapl, { kind: 'security' })).toBe(true);
    expect(matchesFilters(aapl, { kind: 'indicator' })).toBe(false);
  });

  it('filters by asset class (case-insensitive)', () => {
    expect(matchesFilters(aapl, { class: 'equity' })).toBe(true);
    expect(matchesFilters(aapl, { class: 'crypto' })).toBe(false);
  });

  it('filters by market', () => {
    expect(matchesFilters(aapl, { market: 'us' })).toBe(true);
    expect(matchesFilters(aapl, { market: 'pk' })).toBe(false);
  });

  it('matches asset by exact or prefix symbol', () => {
    expect(matchesFilters(aapl, { asset: 'aapl' })).toBe(true);
    expect(matchesFilters(aapl, { asset: 'aa' })).toBe(true);
    expect(matchesFilters(aapl, { asset: 'msft' })).toBe(false);
  });
});
