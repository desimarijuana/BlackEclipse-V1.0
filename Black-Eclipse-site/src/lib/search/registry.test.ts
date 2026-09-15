import { describe, it, expect, beforeEach } from 'vitest';
import { resolveQuery } from './resolver';
import { getAllActions, getAllPages, getInstrumentByAlias, getPage } from './registry';

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

  it('exposes every registered page with a destination (the palette nav list)', () => {
    const pages = getAllPages();
    // The whole app is reachable from the palette's generated "Go to" group.
    expect(pages.length).toBeGreaterThanOrEqual(11);
    expect(pages.every((p) => Boolean(p.title && p.destination?.tab))).toBe(true);
    const tabs = new Set(pages.map((p) => p.destination.tab));
    for (const tab of ['chat', 'dashboard', 'discovery', 'portfolio', 'journal', 'news', 'heatmap', 'economics', 'alerts', 'settings', 'market-workspace']) {
      expect(tabs.has(tab as never)).toBe(true);
    }
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

  it('registers parameterized alert/watch actions that navigate to their tab', () => {
    const actions = getAllActions();
    const alert = actions.find((a) => a.id === 'act-alert-symbol');
    const watch = actions.find((a) => a.id === 'act-watch-symbol');
    expect(alert?.verb).toBe('alert');
    expect(alert?.run({ query: 'alert aapl', normalized: 'alert aapl' })?.tab).toBe('alerts');
    expect(watch?.verb).toBe('watch');
    expect(watch?.run({ query: 'watch aapl', normalized: 'watch aapl' })?.tab).toBe('dashboard');
  });

  it('never offers a requiresArg command as a bare paletted action', () => {
    // "alert" and "watch" must only run with a symbol, via the param path.
    const res = resolveQuery('alert');
    expect(res.actions.some((a) => a.id === 'act-alert-symbol')).toBe(false);
    expect(res.items.some((i) => i.entity.id === 'act-alert-symbol')).toBe(false);
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

  it('scopes results with a prefix and exposes parsed grammar', () => {
    const res = resolveQuery('# AAPL');
    expect(res.parsed.scope).toBe('symbol');
    expect(res.items.length).toBeGreaterThan(0);
    expect(res.items.every((r) => r.entity.kind === 'security' || r.entity.kind === 'instrument')).toBe(true);
  });

  it('returns a bare scope with no text and no results', () => {
    const res = resolveQuery('>');
    expect(res.parsed.scope).toBe('action');
    expect(res.items).toEqual([]);
  });

  it('reports a total count and a did-you-mean suggestion', () => {
    const ok = resolveQuery('AAPL');
    expect(ok.total).toBeGreaterThanOrEqual(ok.items.length);

    // Scoping to symbols filters the curated "Portfolio" page out, so nothing
    // resolves and the nearest registry title is offered as a correction.
    const miss = resolveQuery('# portfoloi');
    expect(miss.items.length).toBe(0);
    expect(miss.suggestion?.toLowerCase()).toContain('portfolio');
  });

  it('flags a bare "?" as the syntax help request', () => {
    const res = resolveQuery('?');
    expect(res.showHelp).toBe(true);
    expect(res.items).toEqual([]);
  });

  it('applies class: operators', () => {
    const res = resolveQuery('class:crypto btc');
    expect(res.items.length).toBeGreaterThan(0);
    expect(res.items.every((r) => r.entity.assetClass === 'crypto')).toBe(true);
  });
});
