import { describe, it, expect } from 'vitest';
import { expandTerms, resolveQuery } from './resolver';

describe('expandTerms', () => {
  it('expands commodity synonyms to their symbols', () => {
    expect(expandTerms('gold price')).toContain('xauusd');
    expect(expandTerms('crude oil')).toContain('cl');
    expect(expandTerms('silver')).toContain('xag');
  });

  it('expands macro phrasing to indicator symbols', () => {
    expect(expandTerms('us jobs data')).toContain('nfp');
    expect(expandTerms('inflation')).toContain('cpi');
    expect(expandTerms('fed rate')).toContain('fomc');
  });

  it('returns nothing for unrelated queries', () => {
    expect(expandTerms('zzzz')).toEqual([]);
  });
});

describe('resolveQuery — synonym expansion', () => {
  it('resolves "gold" to the gold instrument via expansion or alias', () => {
    const res = resolveQuery('gold price now');
    expect(res.items.some((r) => r.entity.symbol === 'XAUUSD')).toBe(true);
  });
});

describe('resolveQuery — related rows', () => {
  it('offers cross-entity pivots for an exact instrument', () => {
    const res = resolveQuery('AAPL');
    expect(res.related.length).toBeGreaterThan(0);
    expect(res.related.some((r) => r.destination.tab === 'news')).toBe(true);
    expect(res.related.every((r) => r.destination.params?.symbol === 'AAPL')).toBe(true);
  });

  it('does not offer related rows inside a scoped symbol search', () => {
    const res = resolveQuery('# AAPL');
    expect(res.related).toEqual([]);
  });
});
