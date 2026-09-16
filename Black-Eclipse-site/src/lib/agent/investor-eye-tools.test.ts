import { describe, it, expect, vi, beforeEach } from 'vitest';

// Investor Eye agent tools (the AI Analyst). Prisma, the world-state assembly
// and the economic fetch layer are mocked so the tests never touch jdds.db or
// the network. The point is the tool CONTRACT + honest output, not the data.

const eventRows = [
  {
    id: 'ev1',
    dedupKey: 'dk1',
    title: 'US imposes new sanctions on Russian banks',
    summary: 'New measures announced',
    eventType: 'sanction',
    severity: 'high',
    channels: JSON.stringify(['Trade & Tariffs']),
    commodities: JSON.stringify([]),
    sectors: JSON.stringify(['Financials']),
    securities: JSON.stringify([]),
    countries: JSON.stringify(['US', 'RU']),
    lon: -98.5,
    lat: 39.8,
    confidence: 0.8,
    sourceCount: 3,
    sources: JSON.stringify([{ id: 'reuters.com', name: 'reuters.com', url: 'https://reuters.com/x' }]),
    primarySource: 'gdelt',
    publishedAt: new Date('2026-09-15T10:00:00.000Z'),
    firstSeen: new Date('2026-09-15T10:05:00.000Z'),
    lastUpdated: new Date('2026-09-15T10:05:00.000Z'),
    status: 'active',
  },
];

vi.mock('@/lib/db', () => ({
  prisma: {
    geopoliticalEvent: {
      findMany: vi.fn(async () => eventRows),
      findFirst: vi.fn(async ({ where }: { where: { OR?: Array<Record<string, string>> } }) => {
        const ids = where.OR ?? [];
        const match = ids.some((o) => o.id === 'ev1' || o.dedupKey === 'dk1');
        return match ? eventRows[0] : null;
      }),
      count: vi.fn(async () => 1),
    },
    relationship: {
      findMany: vi.fn(async () => [
        {
          edgeKey: 'country:US|co_mentioned|country:RU',
          fromKind: 'country', fromId: 'US', fromName: 'United States',
          toKind: 'country', toId: 'RU', toName: 'Russia',
          relation: 'co_mentioned', relationClass: 'OBSERVED', weight: 2,
          evidence: JSON.stringify([{ eventId: 'ev1' }]), provenance: 'LIVE',
          lastSeen: new Date(),
        },
      ]),
    },
    sourceRun: { findMany: vi.fn(async () => []) },
    systemConfig: { findUnique: vi.fn(async () => null), upsert: vi.fn(async () => ({})) },
    indexQuote: { findMany: vi.fn(async () => []) },
  },
  yieldToEventLoop: () => Promise.resolve(),
}));

vi.mock('@/lib/scraper/fetchers/yfinance', () => ({
  fetchYahooBatchQuote: vi.fn(async () => []),
}));

// `assembleState` normally runs the full source ingestion (GDELT/USGS). The
// tools must be tested against a deterministic in-memory state — never the
// network — so it is replaced with a fixed world state.
vi.mock('@/lib/investor-eye/state', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/investor-eye/state')>();
  const events = [
    {
      id: 'ev1', dedupKey: 'dk1',
      title: 'US imposes new sanctions on Russian banks',
      eventType: 'sanction', severity: 'high',
      channels: ['Trade & Tariffs'], commodities: [], sectors: ['Financials'], securities: [],
      countries: ['US', 'RU'], lon: -98.5, lat: 39.8,
      confidence: 0.8, sourceCount: 3, sources: [], primarySource: 'gdelt',
      publishedAt: '2026-09-15T10:00:00.000Z',
    },
  ];
  return {
    ...actual,
    assembleState: vi.fn(async () => ({
      generatedAt: '2026-09-15T12:00:00.000Z',
      windowHours: 24,
      events,
      countries: [],
      markets: [],
      status: { provenance: 'UNAVAILABLE' as const, updatedAt: null, label: 'DATA UNAVAILABLE', sources: [] },
      eventsUnavailable: true,
      lastKnownAt: null,
    })),
  };
});

vi.mock('@/lib/investor-eye/phase2', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/investor-eye/phase2')>();
  return {
    ...actual,
    buildCountryDetail: vi.fn(async (iso2: string) =>
      iso2 === 'US'
        ? { iso2, name: 'United States', region: 'North America', metrics: [{ id: 'inflation', label: 'Inflation (YoY)', value: 3.35, unit: '%', asOf: null }], provenance: 'LIVE' as const }
        : { iso2, name: iso2, metrics: [], provenance: 'UNAVAILABLE' as const }
    ),
    buildCompanies: vi.fn(async () => []),
  };
});

describe('investor-eye agent tools', () => {
  beforeEach(() => vi.clearAllMocks());

  it('exposes the expected read-only tool set', async () => {
    const { INVESTOR_EYE_TOOLS } = await import('./investor-eye-tools');
    const names = INVESTOR_EYE_TOOLS.map((t) => t.name).sort();
    expect(names).toEqual([
      'get_country_intelligence',
      'get_event_detail',
      'get_portfolio_exposure',
      'get_relationships',
      'get_risk_state',
      'get_world_events',
      'get_world_markets',
    ]);
  });

  it('registers the tools alongside the built-ins', async () => {
    const { TOOLS, getTool, toolSchemas } = await import('./tools');
    const names = TOOLS.map((t) => t.name);
    expect(names).toContain('get_price');
    expect(names).toContain('get_world_events');
    expect(names).toContain('get_relationships');
    expect(getTool('get_world_events')).toBeDefined();
    expect(toolSchemas().some((s) => s.function.name === 'get_country_intelligence')).toBe(true);
  });

  it('get_world_events reports events with provenance and confidence', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_world_events')!.execute({ hours: 168 });
    expect(out).toContain('sanctions');
    expect(out).toContain('LIVE');
    expect(out).toContain('confidence');
    expect(out).toContain('US');
    expect(out).toContain('RU');
  });

  it('get_world_events is honest about an empty observed window', async () => {
    const { prisma } = await import('@/lib/db');
    vi.mocked(prisma.geopoliticalEvent.findMany).mockResolvedValueOnce([]);
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_world_events')!.execute({ hours: 24, country: 'PK' });
    expect(out).toContain('No Investor Eye events');
    expect(out.toLowerCase()).toContain('observed empty result');
  });

  it('get_country_intelligence returns metrics and events for a known country', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_country_intelligence')!.execute({ country: 'US' });
    expect(out).toContain('United States');
    expect(out).toContain('Inflation');
    expect(out).toContain('3.35');
  });

  it('get_country_intelligence accepts a country name', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_country_intelligence')!.execute({ country: 'Pakistan' });
    expect(out).toContain('Pakistan');
  });

  it('get_country_intelligence rejects an unknown country honestly', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_country_intelligence')!.execute({ country: 'Atlantis' });
    expect(out).toContain('Unknown country');
  });

  it('get_world_markets is honest when no observations exist', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_world_markets')!.execute({});
    expect(out).toContain('No market observations');
  });

  it('get_event_detail returns facts plus evidence by dedupKey', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_event_detail')!.execute({ id: 'dk1' });
    expect(out).toContain('sanctions');
    expect(out).toContain('Confidence');
    expect(out).toContain('reuters.com');
  });

  it('get_event_detail handles an unknown id', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_event_detail')!.execute({ id: 'nope' });
    expect(out).toContain('No event found');
  });

  it('get_relationships resolves a country and labels relation classes', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_relationships')!.execute({ entity: 'US' });
    expect(out).toContain('United States');
    expect(out).toContain('Russia');
    expect(out).toContain('observed');
    expect(out.toLowerCase()).toContain('potential exposure');
  });

  it('get_relationships is honest when the entity is unknown', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_relationships')!.execute({ entity: 'zzzzzz' });
    expect(out).toContain('No graph node matches');
  });

  it('get_portfolio_exposure computes exposure and never gives advice', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const holdings = JSON.stringify([
      { symbol: 'AAPL', weight: 0.6, country: 'US', sector: 'Technology' },
      { symbol: 'TSM', weight: 0.4, country: 'TW', sector: 'Technology' },
    ]);
    const out = await getInvestorEyeTool('get_portfolio_exposure')!.execute({ holdings });
    expect(out).toContain('EXPOSURE ONLY');
    expect(out).toContain('US');
    expect(out).toContain('60.0%');
    expect(out.toLowerCase()).toContain('not a prediction');
  });

  it('get_portfolio_exposure handles malformed holdings JSON', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_portfolio_exposure')!.execute({ holdings: 'not json' });
    expect(out).toContain('Invalid holdings JSON');
  });

  it('get_risk_state returns decomposable components with drivers', async () => {
    const { getInvestorEyeTool } = await import('./investor-eye-tools');
    const out = await getInvestorEyeTool('get_risk_state')!.execute({ hours: 24 });
    expect(out).toContain('Conflict Risk');
    expect(out).toContain('Trade Risk');
    expect(out.toLowerCase()).toContain('not a market forecast');
  });
});
