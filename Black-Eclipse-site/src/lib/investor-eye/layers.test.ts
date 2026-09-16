import { describe, it, expect } from 'vitest';
import { buildAllLayers, buildEventsLayer, buildMarketsLayer, buildEconomyLayer, buildTradeLayer, buildConflictLayer, buildEnergyLayer, buildWeatherLayer, LAYER_META, LAYER_GROUPS, ALL_LAYER_IDS, groupedLayerIds, layerColor, SEVERITY_COLORS, SEVERITY_ORDER } from './layers';
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

  it('colour-codes every layer from a declared group', () => {
    const groupIds = new Set(LAYER_GROUPS.map((g) => g.id));
    for (const id of ALL_LAYER_IDS) {
      const meta = LAYER_META[id];
      expect(groupIds.has(meta.group)).toBe(true);
      // Every layer resolves to a real hex accent (its own or its group's).
      expect(layerColor(id)).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.hint.length).toBeGreaterThan(0);
    }
  });

  it('groups layers without losing any, and shares a palette with the legend', () => {
    const grouped = groupedLayerIds().flatMap((g) => g.ids);
    expect(new Set(grouped)).toEqual(new Set(ALL_LAYER_IDS));
    // Distinct colours within a group; severity symbols are not all the same.
    for (const { group, ids } of groupedLayerIds()) {
      expect(group.color).toMatch(/^#[0-9a-f]{6}$/i);
      const colors = ids.map((id) => LAYER_META[id].color);
      expect(new Set(colors).size).toBe(colors.length);
    }
    expect(SEVERITY_ORDER.map((s) => SEVERITY_COLORS[s]).filter(Boolean)).toHaveLength(4);
  });

  it('assigns a marker shape to point layers and none to fills', () => {
    expect(LAYER_META.conflict.symbol).toBeDefined();
    expect(LAYER_META.weather.symbol).toBe('triangle');
    expect(LAYER_META.economy.symbol).toBeUndefined();
    expect(LAYER_META.risk.symbol).toBeUndefined();
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

  it('selects the underlying event when a line is clicked', () => {
    const picked: NormalizedEvent[] = [];
    const layer = buildTradeLayer(
      [event({ id: 't1', eventType: 'trade', countries: ['US', 'CN'] })],
      countries,
      (e) => picked.push(e),
    );
    layer.onClick!(layer.data()[0]);
    expect(picked[0]?.id).toBe('t1');
  });
});

describe('category event layers', () => {
  // Regression: the category layers (conflict/weather/energy) rendered a tooltip
  // but had no onClick, so clicking a pin did nothing — which is exactly the
  // "tell me what this is" interaction users reach for first.
  it('conflict, energy and weather select their event on click', () => {
    const events = [
      event({ id: 'c1', eventType: 'conflict', lon: 10, lat: 20 }),
      event({ id: 'e1', eventType: 'energy', lon: 11, lat: 21 }),
      event({ id: 'w1', eventType: 'natural_disaster', lon: 12, lat: 22 }),
    ];
    const cases = [
      { layer: buildConflictLayer(events, (e) => picked.push(e)), id: 'c1' },
      { layer: buildEnergyLayer(events, (e) => picked.push(e)), id: 'e1' },
      { layer: buildWeatherLayer(events, (e) => picked.push(e)), id: 'w1' },
    ];
    const picked: NormalizedEvent[] = [];
    for (const c of cases) {
      expect(c.layer.data()).toHaveLength(1);
      expect(c.layer.onClick).toBeDefined();
      c.layer.onClick!(c.layer.data()[0]);
    }
    expect(picked.map((e) => e.id)).toEqual(['c1', 'e1', 'w1']);
  });

  it('buildAllLayers wires selection into every event layer', () => {
    const picked: NormalizedEvent[] = [];
    const layers = buildAllLayers({
      state: state([event({ id: 'x1', eventType: 'conflict', lon: 1, lat: 2 })]),
      onSelectEvent: (e) => picked.push(e),
    });
    for (const id of ['events', 'conflict', 'energy', 'weather']) {
      const layer = layers.find((l) => l.id === id);
      expect(layer?.onClick).toBeDefined();
      if (layer && layer.data().length > 0) layer.onClick!(layer.data()[0]);
    }
    expect(picked.length).toBeGreaterThan(0);
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
