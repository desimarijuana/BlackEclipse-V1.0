import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { resolveQuery } from './resolver';
import { __setEventsForTest } from './events';

const FUNDS = [
  { id: 'demo-core-growth', name: 'Core Growth', icon: 'Rocket', accent: '#34d399', createdAt: '2026-01-15', seeded: true, transactions: [] },
  { id: 'demo-tech-satellite', name: 'Tech Satellite', icon: 'Gem', accent: '#f472b6', createdAt: '2026-03-10', seeded: true, transactions: [] },
];

beforeEach(() => {
  __setEventsForTest([]);
  // @ts-expect-error stub browser window for node test env
  globalThis.window = {};
  // @ts-expect-error stub localStorage for node test env
  globalThis.localStorage = {
    _d: { 'be_portfolio_funds_v1': JSON.stringify(FUNDS) },
    getItem(k: string) { return this._d[k] ?? null; },
    setItem(k: string, v: string) { this._d[k] = v; },
  };
});

afterEach(() => {
  // @ts-expect-error cleanup stubbed window
  delete globalThis.window;
  // @ts-expect-error cleanup stubbed localStorage
  delete globalThis.localStorage;
});

describe('fund resolution', () => {
  it('resolves a fund by exact name', () => {
    const r = resolveQuery('Core Growth');
    const fund = r.items.find((i) => i.entity.kind === 'user');
    expect(fund).toBeDefined();
    expect(fund?.entity.title).toBe('Core Growth');
    expect(fund?.entity.destination.params?.fund).toBe('demo-core-growth');
  });

  it('resolves a fund by the word "fund"', () => {
    const r = resolveQuery('fund');
    const fund = r.items.find((i) => i.entity.kind === 'user');
    expect(fund).toBeDefined();
  });

  it('resolves a fund by fuzzy name', () => {
    const r = resolveQuery('Core Growt');
    const fund = r.items.find((i) => i.entity.kind === 'user');
    expect(fund).toBeDefined();
  });
});
