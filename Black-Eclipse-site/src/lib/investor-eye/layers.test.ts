import { describe, it, expect } from 'vitest';
import { buildAllLayers, buildEventsLayer, buildMarketsLayer, buildEconomyLayer, buildTradeLayer, LAYER_META, ALL_LAYER_IDS } from './layers';
import type { CountrySummary, InvestorEyeState, MarketObservation, NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'Event',
    eventType: 'trade',
    severity: 'medium',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['US'],
    lon: -98.5,
    lat: 39.8,
    confidence: 0.5,
    sourceCount: 1,
    sources: [],
    primarySource: 'gdelt',
    publishedAt: '2026-09-15T10:00:00.000Z',
    ...overrides,
  };
}

const countries: CountrySummary[] = [
  { iso2: 'US', name: 'United States', region: 'North America', lon: -98.5, lat: 39.8, eventCount: 2, markets: [] },
  { iso2: 'CN', name: 'China', region: 'East Asia', lon: 104.2, lat: 35.9, eventCount: 1, markets: [] },
];

const markets: MarketObservation[] = [
  { marketId: 'US', iso2: 'US', name: 'United States', symbol: 'S&P 500', price: 5000, changePct: 0.7, provenance: 'LIVE' },
];

function state(events: NormalizedEvent[]): InvestorEyeState {
  return {
    generatedAt: '2026-09-15T10:00:00.000Z',
    windowHours: 24,
    events,
    countries,
    markets,
    status: { provenance: 'LIVE', updatedAt: '2026-09-15T10:00:00.000Z', label: 'UPDATED 0s AGO', sources: [] },
  };
}

describe('layer registry', () => {
  it('exposes metadata for every layer id', () => {
    for (const id of ALL_LAYER_IDS) {
      expect(LAYER_META[id]).toBeDefined();
      expect(LAYER_META[id].name.length).toBeGreaterThan(0);
    }
  });

  it('marks events and markets as Phase 1', () => {
    expect(LAYER_META.events.phase).toBe(1);
    expect(LAYER_META.markets.phase).toBe(1);
    expect(LAYER_META.trade.phase).toBe(2);
  });
});

describe('buildEventsLayer', () => {
  it('only plots events with coordinates', () => {
    const layer = buildEventsLayer([
      event({ id: 'a', lon: -98.5, lat: 39.8 }),
      event({ id: 'b', lon: undefined, lat: undefined }),
    ]);
    expect(layer.data()).toHaveLength(1);
  });

  it('aggregates dense events instead of emitting raw points', () => {
    const events = Array.from({ length: 50 }, (_, i) =>
      event({ id: `e${i}`, lon: 10 + i * 0.001, lat: 20 + i * 0.001 }),
    );
    const layer = buildEventsLayer(events);
    const data = layer.data();
    expect(data.length).toBeLessThan(events.length);
    expect((data[0].data as { cluster: { count: number } }).cluster.count).toBeGreaterThan(1);
  });

  it('produces a tooltip that separates observed facts from potential exposure', () => {
    const layer = buildEventsLayer([event({ channels: ['Energy'] })]);
    const tip = layer.tooltip!(layer.data()[0]);
    expect(tip.rows.some((r) => r.label === 'Type')).toBe(true);
    expect(tip.note?.toLowerCase()).toContain('potential');
  });

  it('invokes the select callback on click', () => {
    const clicked: NormalizedEvent[] = [];
    const layer = buildEventsLayer([event()], (e) => { clicked.push(e); });
    layer.onClick?.(layer.data()[0]);
    expect(clicked[0]?.id).toBe('e1');
  });
});

describe('buildMarketsLayer', () => {
  it('positions markets by their country centroid', () => {
    const layer = buildMarketsLayer(markets, countries);
    const data = layer.data();
    expect(data).toHaveLength(1);
    expect(data[0].lon).toBe(-98.5);
  });

  it('omits markets without a resolvable country', () => {
    const layer = buildMarketsLayer([{ ...markets[0], iso2: undefined }], countries);
    expect(layer.data()).toHaveLength(0);
  });
});

describe('buildEconomyLayer', () => {
  it('only includes finite values and computes a range', () => {
    const layer = buildEconomyLayer({ US: 3, GB: 2, XX: Number.NaN }, 'Inflation');
    const data = layer.data();
    expect(data).toHaveLength(2);
    const tooltip = layer.tooltip!(data[0]);
    expect(tooltip.title).toBeDefined();
  });
});

describe('buildTradeLayer', () => {
  it('emits lines only when one event names both endpoints', () => {
    const layer = buildTradeLayer([event({ eventType: 'trade', countries: ['US', 'CN'] })], countries);
    expect(layer.data()).toHaveLength(1);
  });

  it('ignores non-trade events and single-country events', () => {
    expect(buildTradeLayer([event({ eventType: 'election', countries: ['US', 'CN'] })], countries).data()).toHaveLength(0);
    expect(buildTradeLayer([event({ eventType: 'trade', countries: ['US'] })], countries).data()).toHaveLength(0);
  });
});

describe('buildAllLayers', () => {
  it('builds the Phase 1 layers by default and adds Phase 2 layers only with data', () => {
    const layers = buildAllLayers({ state: state([event()]) });
    const ids = layers.map((l) => l.id);
    expect(ids).toContain('events');
    expect(ids).toContain('markets');
    expect(ids).toContain('conflict');
    expect(ids).not.toContain('economy');
    expect(ids).not.toContain('companies');
    expect(ids).not.toContain('portfolio');
  });

  it('adds economy, companies and portfolio when inputs exist', () => {
    const layers = buildAllLayers({
      state: state([event()]),
      economicValues: { metricLabel: 'Inflation', values: { US: 3 } },
      companies: [{ symbol: 'AAPL', name: 'Apple', iso2: 'US', lon: -98.5, lat: 39.8 }],
      portfolioExposure: [{ iso2: 'US', weight: 0.5 }],
    });
    const ids = layers.map((l) => l.id);
    expect(ids).toContain('economy');
    expect(ids).toContain('companies');
    expect(ids).toContain('portfolio');
  });
});
