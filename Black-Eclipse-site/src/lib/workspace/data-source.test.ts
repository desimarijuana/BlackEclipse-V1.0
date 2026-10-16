import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseSource, columnsFromRows, resolveSource } from './data-source';

const READ = {
  portfolio: { id: 'pf_x', name: 'UwU Portfolio', baseCurrency: 'PKR' },
  positions: [
    { symbol: 'AAPL', quantity: '10', averageCost: '100', price: '150', marketValueBase: '1500', unrealizedPnlBase: '500', weight: 100, currency: 'USD' },
  ],
  cash: { baseCurrency: 'USD', balance: '0', netDeposits: '0', dividends: '0' },
  valuation: { baseCurrency: 'USD', investedValue: '1000', cash: '0', totalValue: '1500', dataQuality: { status: 'OK', missingPrices: [], stalePrices: [], missingFX: [], unpricedPositions: [], warnings: [] } },
  dataQuality: { status: 'OK', missingPrices: [], stalePrices: [], missingFX: [], unpricedPositions: [], warnings: [] },
  calculationVersion: '1',
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('resolveSource (portfolio)', () => {
  it('resolves a positions source into rows with columns', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(READ), { status: 200 })));
    const res = await resolveSource('portfolio:pf_x:positions');
    expect(res.kind).toBe('rows');
    expect(res.provenance).toBe('LIVE');
    expect(res.rows?.[0]).toMatchObject({ symbol: 'AAPL', quantity: '10' });
    expect(res.columns?.map((c) => c.key)).toContain('marketValueBase');
  });

  it('resolves a summary metric field into a value', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(READ), { status: 200 })));
    const res = await resolveSource('portfolio:pf_x:summary.totalValue');
    expect(res.kind).toBe('value');
    expect(res.value).toBe('1500');
  });

  it('reports UNAVAILABLE when the runtime rejects the read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'runtime unavailable' }), { status: 503 })));
    const res = await resolveSource('portfolio:pf_x:positions');
    expect(res.kind).toBe('unavailable');
    expect(res.provenance).toBe('UNAVAILABLE');
    expect(res.detail).toContain('unavailable');
  });

  it('reports UNAVAILABLE for an unrecognised source without fetching', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const res = await resolveSource('nonsense');
    expect(res.kind).toBe('unavailable');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('resolveSource (tasks / artifacts / research / jdds)', () => {
  it('resolves tasks:list into rows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true, tasks: [{ id: 't1', title: 'Ship it', status: 'RUNNING', priority: 'high', updatedAt: '2026-01-01' }] }), { status: 200 })));
    const res = await resolveSource('tasks:list');
    expect(res.kind).toBe('rows');
    expect(res.rows?.[0]).toMatchObject({ title: 'Ship it' });
  });

  it('resolves artifacts:list into rows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true, artifacts: [{ id: 'a1', displayName: 'Report.pdf', category: 'document' }] }), { status: 200 })));
    const res = await resolveSource('artifacts:list');
    expect(res.kind).toBe('rows');
    expect(res.columns?.map((c) => c.key)).toContain('displayName');
  });

  it('resolves jdds:search into rows or a single field value', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ suggestions: [{ symbol: 'AAPL', name: 'Apple Inc.', price: 190.5, currency: 'USD' }] }), { status: 200 })));
    const rows = await resolveSource('jdds:search:apple');
    expect(rows.kind).toBe('rows');
    const value = await resolveSource('jdds:search:apple.price');
    expect(value.kind).toBe('value');
    expect(value.value).toBe(190.5);
  });
});

describe('parseSource', () => {
  it('parses a table source', () => {
    expect(parseSource('portfolio:pf_7586246984d44b11bfb8:positions')).toEqual({
      family: 'portfolio', portfolioId: 'pf_7586246984d44b11bfb8', view: 'positions',
    });
  });

  it('parses a metric field suffix', () => {
    expect(parseSource('portfolio:pf_x:summary.totalValue')).toEqual({
      family: 'portfolio', portfolioId: 'pf_x', view: 'summary', field: 'totalValue',
    });
  });

  it('parses the market / news / agent families', () => {
    expect(parseSource('market:quote:AAPL,MSFT')).toEqual({ family: 'market', kind: 'quote', arg: 'AAPL,MSFT', field: undefined });
    expect(parseSource('market:indices:US')).toEqual({ family: 'market', kind: 'indices', arg: 'US', field: undefined });
    expect(parseSource('market:price:AAPL.close')).toEqual({ family: 'market', kind: 'price', arg: 'AAPL', field: 'close' });
    expect(parseSource('news:latest')).toEqual({ family: 'news', arg: 'latest' });
    expect(parseSource('agent:activity')).toEqual({ family: 'agent', arg: 'activity' });
  });

  it('parses the tasks / artifacts / research / jdds families', () => {
    expect(parseSource('tasks:list')).toEqual({ family: 'tasks', view: 'list' });
    expect(parseSource('tasks:plans')).toEqual({ family: 'tasks', view: 'plans' });
    expect(parseSource('artifacts:list')).toEqual({ family: 'artifacts', view: 'list' });
    expect(parseSource('research:list')).toEqual({ family: 'research', view: 'list' });
    expect(parseSource('jdds:search:apple')).toEqual({ family: 'jdds', view: 'search', arg: 'apple', field: undefined });
    expect(parseSource('jdds:search:apple.price')).toEqual({ family: 'jdds', view: 'search', arg: 'apple', field: 'price' });
    expect(parseSource('tasks:nope')).toBeNull();
    expect(parseSource('jdds:search')).toBeNull();
  });

  it('rejects unknown families, unknown views and malformed strings', () => {
    expect(parseSource('portfolio.positions')).toBeNull();
    expect(parseSource('foo:bar:baz')).toBeNull();
    expect(parseSource('market:nope:AAPL')).toBeNull();
    expect(parseSource('market:quote')).toBeNull();
    expect(parseSource('portfolio:pf_x:not-a-view')).toBeNull();
    expect(parseSource('portfolio::positions')).toBeNull();
    expect(parseSource('')).toBeNull();
    expect(parseSource(null)).toBeNull();
  });
});

describe('columnsFromRows', () => {
  it('prefers the known field order and infers alignment', () => {
    const cols = columnsFromRows(
      [{ tradeDate: '2024-01-01', type: 'BUY', quantity: 3 }],
      ['tradeDate', 'type', 'quantity'],
    );
    expect(cols.map((c) => c.key)).toEqual(['tradeDate', 'type', 'quantity']);
    expect(cols.find((c) => c.key === 'quantity')?.align).toBe('right');
  });
});
