import { describe, it, expect } from 'vitest';
import { buildAllLayers, buildEventsLayer, buildMarketsLayer, buildEconomyLayer, buildTradeLayer, buildConflictLayer, buildEnergyLayer, buildWeatherLayer, buildFiresLayer, buildShippingLayer, buildCommoditiesLayer, buildEventHeatmapLayer, LAYER_META, LAYER_GROUPS, ALL_LAYER_IDS, groupedLayerIds, layerColor, layerSymbol, SYMBOL_PATHS, SEVERITY_COLORS, SEVERITY_ORDER } from './layers';
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

  it('assigns a marker glyph to point layers and none to fills', () => {
    expect(LAYER_META.conflict.glyph).toBe('blast');
    expect(LAYER_META.weather.glyph).toBe('seismic');
    expect(LAYER_META.fires.glyph).toBe('flame');
    // Fills paint regions; a point glyph would be meaningless on them.
    expect(LAYER_META.economy.glyph).toBeUndefined();
    expect(LAYER_META.economy.symbol).toBeUndefined();
  });
});

describe('domain layers match type OR channel', () => {
  // The regression that motivated this: an event is assigned ONE type but many
  // channels, so a Red Sea attack typed `conflict` still carries the Shipping
  // channel. Matching only on type drew a fraction of the real signal —
  // measured live: 204 shipping-channel events vs 26 shipping-typed.

  it('surfaces a conflict event in the shipping layer when it has the channel', () => {
    const e = event({ id: 's1', eventType: 'conflict', channels: ['Shipping & Logistics'], lon: 43, lat: 12 });
    expect(buildShippingLayer([e]).data()).toHaveLength(1);
    // And it stays in the conflict layer — a layer is a lens, not an exclusive bucket.
    expect(buildConflictLayer([e]).data()).toHaveLength(1);
  });

  it('picks up an energy-channel event typed something else', () => {
    const e = event({ id: 'en1', eventType: 'monetary', channels: ['Energy'], lon: 50, lat: 26 });
    expect(buildEnergyLayer([e]).data()).toHaveLength(1);
  });

  it('does not put an unrelated event in a domain layer', () => {
    const e = event({ id: 'x1', eventType: 'election', channels: [], commodities: [], lon: 1, lat: 1 });
    expect(buildShippingLayer([e]).data()).toHaveLength(0);
    expect(buildEnergyLayer([e]).data()).toHaveLength(0);
    expect(buildCommoditiesLayer([e]).data()).toHaveLength(0);
  });

  it('commodities layer is purely commodity-driven, regardless of type', () => {
    const oil = event({ id: 'c1', eventType: 'conflict', commodities: ['Crude Oil'], lon: 2, lat: 2 });
    const none = event({ id: 'c2', eventType: 'energy', commodities: [], lon: 3, lat: 3 });
    const data = buildCommoditiesLayer([oil, none]).data();
    expect(data).toHaveLength(1);
    expect((data[0].data as NormalizedEvent).id).toBe('c1');
  });

  it('registers shipping and commodities as real, coloured layers', () => {
    expect(LAYER_META.shipping.group).toBe('flows');
    expect(LAYER_META.commodities.glyph).toBe('ingot');
    expect(layerColor('shipping')).toMatch(/^#[0-9a-f]{6}$/i);
    expect(layerColor('commodities')).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('builds the shipping and commodities layers by default', () => {
    const ids = buildAllLayers({ state: state([event()]) }).map((l) => l.id);
    expect(ids).toContain('shipping');
    expect(ids).toContain('commodities');
  });
});

describe('channel-driven trade lines', () => {
  it('draws a line for a conflict event carrying the Trade channel', () => {
    const e = event({ id: 't2', eventType: 'conflict', channels: ['Trade & Tariffs'], countries: ['US', 'CN'] });
    expect(buildTradeLayer([e], countries).data()).toHaveLength(1);
  });

  it('ignores a multi-country event with no trade signal at all', () => {
    const e = event({ id: 't3', eventType: 'election', channels: [], countries: ['US', 'CN'] });
    expect(buildTradeLayer([e], countries).data()).toHaveLength(0);
  });
});

describe('category glyphs', () => {
  // Every domain layer renders its own silhouette, so a conflict, a fire and an
  // earthquake are told apart by SHAPE, not only by colour.
  it('gives every point layer a distinct category glyph', () => {
    const pointLayers = ['events', 'markets', 'conflict', 'shipping', 'trade', 'energy', 'commodities', 'weather', 'fires', 'companies', 'risk', 'portfolio'] as const;
    const glyphs = pointLayers.map((id) => LAYER_META[id].glyph);
    for (const g of glyphs) expect(g, 'a point layer is missing its glyph').toBeDefined();
    // Distinctness is the entire point: two layers sharing a glyph defeats it.
    expect(new Set(glyphs).size).toBe(glyphs.length);
  });

  it('emits a path:// symbol for a glyph layer, and the primitive otherwise', () => {
    expect(layerSymbol('conflict')).toBe(SYMBOL_PATHS.blast);
    expect(layerSymbol('weather')).toBe(SYMBOL_PATHS.seismic);
    expect(layerSymbol('fires')).toBe(SYMBOL_PATHS.flame);
    // A layer with no glyph falls back to its primitive, then to a circle.
    expect(layerSymbol('nope')).toBe('circle');
  });

  it('declares every glyph as valid SVG path data', () => {
    for (const [name, path] of Object.entries(SYMBOL_PATHS)) {
      expect(path, `${name} must be a path:// symbol`).toMatch(/^path:\/\//);
      // The body must start with a move command, or ECharts' parser draws nothing.
      expect(path.replace('path://', '').trim(), `${name} must start with M`).toMatch(/^M/);
    }
  });

  it('keeps the catch-all events layer visually subordinate', () => {
    // `events` overlays every geolocated event, so its marker must not be a big
    // shape that buries the meaningful category glyphs underneath it.
    expect(LAYER_META.events.glyph).toBe('event');
    expect(SYMBOL_PATHS.event).toBe(SYMBOL_PATHS.event);
    // A dot, not a diamond/star: the path describes a circle.
    expect(SYMBOL_PATHS.event.includes('A')).toBe(true);
  });

  it('draws every cut-out with the opposite winding to its outer shape', () => {
    // A canvas fill uses the NONZERO winding rule. A subpath that is supposed to
    // be a HOLE must run the other way round, or the hole fills in and the glyph
    // collapses to a solid blob — which is exactly how the earthquake layer
    // shipped as a plain dot, the portfolio ring as a disc, and the risk
    // triangle as a solid wedge.
    function signedArea(points: string): number {
      const nums = points.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
      const pts: Array<[number, number]> = [];
      for (let i = 0; i + 1 < nums.length; i += 2) pts.push([nums[i], nums[i + 1]]);
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const [x1, y1] = pts[i];
        const [x2, y2] = pts[(i + 1) % pts.length];
        area += x1 * y2 - x2 * y1;
      }
      return area / 2;
    }
    function subpaths(path: string): string[] {
      return path.replace('path://', '').split(/(?=M)/).filter((s) => s.trim().startsWith('M'));
    }
    /** True when a ring of `M…L…Z` points winds the opposite way to the first. */
    function hasOppositeWinding(path: string): boolean {
      const parts = subpaths(path).filter((s) => !s.includes('A'));
      if (parts.length !== 2) return false;
      // Opposite signs ⇒ opposite winding ⇒ the centre is punched out.
      return Math.sign(signedArea(parts[0])) !== Math.sign(signedArea(parts[1]));
    }

    // `risk` is the one polygonal glyph with a real hole; the glyphs with two
    // subpaths that are NOT holes (a ship's hull + swell, two exchange arrows,
    // two office blocks) deliberately wind the same way, since each subpath is
    // its own solid shape.
    expect(hasOppositeWinding(SYMBOL_PATHS.risk), 'risk renders solid').toBe(true);
    expect(subpaths(SYMBOL_PATHS.risk)).toHaveLength(2);

    // ECharts' arc syntax spells the direction out: sweep-flag 1 is clockwise,
    // 0 is counter-clockwise. A ring glyph must contain BOTH directions, or the
    // hole fills in and it renders as a solid disc. `seismic` alternates ring by
    // ring and `portfolio` has one hole, so both must show both sweeps.
    for (const name of ['seismic', 'portfolio'] as const) {
      const body = SYMBOL_PATHS[name];
      expect(body, `${name} has no clockwise arc`).toMatch(/A\d+,\d+ 0 1,1/);
      expect(body, `${name} has no counter-clockwise arc`).toMatch(/A\d+,\d+ 0 1,0/);
      // Every circle is a PAIR of 180° arcs. A single near-full arc (the form
      // that shipped off-centre and lumpy) has no `A` returning to its start
      // point, so a ring with an odd arc count is the bug.
      const arcs = body.match(/A\d+,\d+/g) ?? [];
      expect(arcs.length % 2, `${name} has an odd arc count`).toBe(0);
    }
  });

  it('keeps the catch-all events layer BEHIND the category glyphs', () => {
    // The events layer draws a dot for every geolocated event. When its zIndex
    // was above the domain layers the dot was painted over the conflict/fire/
    // energy glyphs, which is what made every pin look the same on the map.
    expect(LAYER_META.events.glyph).toBeDefined();
    const eventsZ = buildEventsLayer([event({ id: 'z1' })]).zIndex;
    const domainZ = buildConflictLayer([event({ id: 'z2', eventType: 'conflict' })]).zIndex;
    expect(eventsZ).toBeLessThan(domainZ);
  });
});

describe('hazard layer split (earthquakes vs fires)', () => {
  const quake = event({ id: 'q1', eventType: 'natural_disaster', category: 'earthquake', lon: 10, lat: 20 });
  const fire = event({ id: 'f1', eventType: 'natural_disaster', category: 'fire', lon: 11, lat: 21 });
  // A row persisted before `category` existed — it must not disappear.
  const legacy = event({ id: 'l1', eventType: 'natural_disaster', lon: 12, lat: 22 });

  it('puts earthquakes and fires in separate layers with no overlap', () => {
    const weather = buildWeatherLayer([quake, fire, legacy]).data();
    const fires = buildFiresLayer([quake, fire, legacy]).data();
    expect(weather.map((d) => (d.data as NormalizedEvent).id)).toEqual(['q1', 'l1']);
    expect(fires.map((d) => (d.data as NormalizedEvent).id)).toEqual(['f1']);
  });

  it('keeps a legacy uncategorised hazard in the earthquake layer', () => {
    // No migration: an old row keeps its original layer rather than vanishing.
    const weather = buildWeatherLayer([legacy]).data();
    expect(weather).toHaveLength(1);
  });

  it('registers fires as a hazard layer with its own colour', () => {
    expect(LAYER_META.fires.group).toBe('hazards');
    expect(LAYER_META.fires.color).not.toBe(LAYER_META.weather.color);
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

describe('buildEventHeatmapLayer', () => {
  it('aggregates nearby events and sums their severity weight as intensity', () => {
    // The regression: one datum per raw event rendered a flat wash, because
    // every point had the same ~1px weight. Density must be the SUM of weights
    // so a cluster of critical events is genuinely hotter than a lone low one.
    const criticals = Array.from({ length: 20 }, (_, i) =>
      event({ id: `c${i}`, severity: 'critical', lon: 30 + i * 0.001, lat: 40 + i * 0.001 }),
    );
    const heat = buildEventHeatmapLayer(criticals);
    const data = heat.data();
    expect(data.length).toBeLessThan(criticals.length);
    expect(data[0].value!).toBeCloseTo(20 * 1, 1);
    expect(data[0].severity).toBe('critical');

    const low = buildEventHeatmapLayer([event({ id: 'l1', severity: 'low', lon: -100, lat: 10 })]);
    expect(low.data()[0].value!).toBeCloseTo(0.2, 5);
  });

  it('drops events with no coordinates, like every other point layer', () => {
    const heat = buildEventHeatmapLayer([
      event({ id: 'a', lon: 1, lat: 2 }),
      event({ id: 'b', lon: undefined, lat: undefined }),
    ]);
    expect(heat.data()).toHaveLength(1);
  });

  it('is a heatmap layer in the events group with its own legend glyph', () => {
    expect(buildEventHeatmapLayer([]).type).toBe('heatmap');
    expect(LAYER_META['event-heatmap'].group).toBe('events');
    expect(LAYER_META['event-heatmap'].glyph).toBe('heat');
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

  it('carries the route endpoints and traded goods on each line', () => {
    // A trade line's whole meaning is the pair of endpoints, so the datum must
    // carry them (plus the event key) for the map's selection emphasis and the
    // route tooltip.
    const e = event({ id: 'r1', eventType: 'trade', countries: ['US', 'CN'], commodities: ['Crude Oil'] });
    const d = buildTradeLayer([e], countries).data()[0];
    const payload = d.data as { fromName: string; toName: string; eventKey: string };
    expect(payload.fromName).toBe('United States');
    expect(payload.toName).toBe('China');
    expect(payload.eventKey).toBe('r1');
    const tip = buildTradeLayer([e], countries).tooltip!(d);
    expect(tip.rows.find((r) => r.label === 'Route')?.value).toContain('United States');
    expect(tip.rows.find((r) => r.label === 'Traded goods')?.value).toContain('Crude Oil');
    expect(tip.note?.toLowerCase()).toContain('observed');
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
