import { beforeEach, describe, expect, it, vi } from 'vitest';

// Minimal in-memory FlexSearch stand-in (substring match) so the test exercises
// the LAZY dynamic import + index build without pulling the real library.
class FakeIndex {
  private items = new Map<number, string>();
  constructor(_opts: unknown) {}
  add(id: number, content: string): void {
    this.items.set(id, content.toLowerCase());
  }
  search(q: string, limit = 10): number[] {
    const out: number[] = [];
    for (const [id, c] of this.items) {
      if (c.includes(q.toLowerCase())) out.push(id);
      if (out.length >= limit) break;
    }
    return out;
  }
}

vi.mock('flexsearch', () => ({ default: { Index: FakeIndex } }));

const payload = {
  version: '2.0.0',
  count: 2,
  builtAt: Date.now(),
  symbols: ['AAPL', 'MSFT'],
  names: ['Apple Inc.', 'Microsoft Corp.'],
  markets: ['US', 'US'],
  classes: ['equity', 'equity'],
};

describe('search/universe lazy index', () => {
  beforeEach(() => {
    vi.resetModules();
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => payload })) as unknown as typeof fetch;
  });

  it('builds the index via the dynamic flexsearch import and serves lookups', async () => {
    const mod = await import('./universe');
    expect(mod.isUniverseLoaded()).toBe(false);
    await mod.loadUniverseIndex();
    expect(mod.isUniverseLoaded()).toBe(true);
    expect(mod.universeCount()).toBe(2);
    expect(mod.getUniverseBySymbol('aapl')?.symbol).toBe('AAPL');
    expect(mod.searchUniverse('app').map((r) => r.symbol)).toContain('AAPL');
  });
});
