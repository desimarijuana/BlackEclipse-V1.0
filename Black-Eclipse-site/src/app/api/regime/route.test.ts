import { beforeEach, describe, expect, it, vi } from 'vitest';

// The route reads the DB synchronously via prisma and fetches the economics
// calendar. Everything is stubbed so the test exercises ONLY the new
// component-cache behaviour (the response contract is unchanged by caching).
const indexQuoteFindMany = vi.hoisted(() => vi.fn(async () => [] as unknown[]));
const indexQuoteFindFirst = vi.hoisted(() => vi.fn(async () => null));
const assetFindMany = vi.hoisted(() => vi.fn(async () => [] as unknown[]));
const macroFindMany = vi.hoisted(() => vi.fn(async () => [] as unknown[]));
const newsFindMany = vi.hoisted(() => vi.fn(async () => [] as unknown[]));

vi.mock('@/lib/db', () => ({
  prisma: {
    indexQuote: { findMany: indexQuoteFindMany, findFirst: indexQuoteFindFirst },
    asset: { findMany: assetFindMany },
    macroSeries: { findMany: macroFindMany },
    newsItem: { findMany: newsFindMany },
  },
}));

vi.mock('@/lib/economics/calendar', () => ({
  fetchEconomicCalendar: vi.fn(async () => ({ events: [] })),
}));

// Keep the real route logic, but replace the pure scoring layer so the test
// does not depend on its internals.
vi.mock('@/lib/regime/scoring', () => ({
  resolveRegimeMarket: (_scope: string, market: string) => market,
  assembleRegime: (input: { scope: string; market: string }) => ({
    scope: input.scope,
    market: input.market,
    builtAt: Date.now(),
  }),
  marketNewsRegions: () => [],
  scoreMacroSurprises: () => null,
  scoreNews: () => null,
  scorePriceBreadth: () => null,
  scoreVolatility: () => null,
}));

beforeEach(() => {
  indexQuoteFindMany.mockClear();
  indexQuoteFindFirst.mockClear();
  assetFindMany.mockClear();
  macroFindMany.mockClear();
  newsFindMany.mockClear();
  vi.resetModules();
});

describe('GET /api/regime component cache', () => {
  it('builds the components once for repeat requests within the TTL', async () => {
    const { GET } = await import('./route');
    const req = () => new Request('http://localhost/api/regime?scope=selected&market=US');

    const first = await GET(req());
    const second = await GET(req());

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    // The expensive read happens once; the second request is served from cache.
    expect(indexQuoteFindMany).toHaveBeenCalledTimes(1);
    expect(newsFindMany).toHaveBeenCalledTimes(1);
  });

  it('caches each market independently', async () => {
    const { GET } = await import('./route');

    await GET(new Request('http://localhost/api/regime?scope=selected&market=US'));
    await GET(new Request('http://localhost/api/regime?scope=global'));

    // US and GLOBAL are distinct keys, so each is built once.
    expect(indexQuoteFindMany).toHaveBeenCalledTimes(2);
  });
});
