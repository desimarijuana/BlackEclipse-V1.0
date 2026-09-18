// ── Investor Eye — map adapter contract ──────────────────────────────────────
// Regression cover for the ECharts boundary. These bugs were invisible to
// `tsc` because the payload is `unknown` at the library edge, and they only
// surfaced as runtime crashes in the browser.

import { describe, it, expect } from 'vitest';
import { buildMapOption, hasDrawableBox, unwrapDatum } from './map-echarts';
import { buildConflictLayer, buildEventsLayer, severityColor, SYMBOL_PATHS } from './layers';
import type { LayerDatum, MapLayer, NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'Event',
    eventType: 'conflict',
    severity: 'high',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['TR'],
    lon: 30,
    lat: 39,
    confidence: 0.5,
    sourceCount: 1,
    sources: [],
    primarySource: 'gdelt',
    publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

describe('unwrapDatum', () => {
  it('unwraps the ECharts wrapper to the LayerDatum', () => {
    const datum: LayerDatum = { id: 'd1', lon: 1, lat: 2, label: 'D', data: event() };
    // ECharts passes its own wrapper carrying `_datum`.
    expect(unwrapDatum({ data: { ...datum, _datum: datum } })).toBe(datum);
  });

  it('accepts a payload that already IS a LayerDatum', () => {
    const datum: LayerDatum = { id: 'd1' };
    expect(unwrapDatum({ data: datum })).toBe(datum);
  });

  it('returns undefined for a missing payload (never throws)', () => {
    expect(unwrapDatum(undefined)).toBeUndefined();
    expect(unwrapDatum({})).toBeUndefined();
  });
});

describe('buildMapOption tooltip formatter', () => {
  // The reported crash: hovering a conflict pin threw
  // "Cannot read properties of undefined (reading 'eventType')" because the
  // formatter read `params.data.data` instead of unwrapping `_datum`.
  function formatterFor(layer: MapLayer) {
    const opt = buildMapOption({ layers: [{ ...layer, enabled: true }] });
    const series = opt.series as unknown as Array<{ id: string; tooltip?: { formatter: (p: unknown) => string } }>;
    const s = series.find((x) => x.id === layer.id);
    if (!s?.tooltip) throw new Error(`no tooltip series for ${layer.id}`);
    return s.tooltip.formatter;
  }

  it('renders a conflict tooltip from the wrapped ECharts payload', () => {
    const layer = buildConflictLayer([event({ id: 'c1', title: 'Shelling reported' })], () => {});
    const datum = layer.data()[0];
    const html = formatterFor(layer)({ data: { ...datum, _datum: datum } });
    expect(html).toContain('Shelling reported');
    expect(html).toContain('conflict');
  });

  it('renders an events tooltip from the wrapped ECharts payload', () => {
    const layer = buildEventsLayer([event({ id: 'x1', title: 'Port strike' })]);
    const datum = layer.data()[0];
    const html = formatterFor(layer)({ data: { ...datum, _datum: datum } });
    expect(html).toContain('Port strike');
  });

  it('degrades to empty instead of throwing on a malformed payload', () => {
    const layer = buildConflictLayer([event()], () => {});
    const fmt = formatterFor(layer);
    expect(() => fmt({ data: undefined })).not.toThrow();
    expect(fmt({ data: undefined })).toBe('');
    // A wrapper whose _datum is a bogus object must still not throw.
    expect(() => fmt({ data: { _datum: {} } })).not.toThrow();
  });
});

describe('buildMapOption globe data shape', () => {
  // `scatter3D` reads a THIRD array element as altitude, which lifted pins off
  // the sphere into radiating spikes; 3D series must send exactly [lon, lat].
  it('omits the value slot in globe mode and keeps it in 2D', () => {
    const layer = buildEventsLayer([event({ id: 'g1', lon: 12, lat: 34 })]);
    const valueOf = (mode: '2d' | 'globe') => {
      const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode });
      const series = opt.series as unknown as Array<{ id: string; data: Array<{ value: number[] }> }>;
      return series.find((s) => s.id === layer.id)!.data[0].value;
    };
    expect(valueOf('globe')).toHaveLength(2);
    expect(valueOf('2d')).toHaveLength(3);
  });
});

describe('buildMapOption globe glow', () => {
  function seriesFor(mode: '2d' | 'globe') {
    const layer = buildEventsLayer([event({ id: 'g2', lon: 12, lat: 34 })]);
    const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode });
    return opt.series as unknown as Array<{
      id: string; type: string; symbol?: string; silent?: boolean;
      itemStyle?: { color?: unknown; opacity?: number };
    }>;
  }

  it('does NOT draw a halo disc over the globe glyphs', () => {
    // A halo is a larger copy of the same shape behind the core. Once glyphs
    // carry the meaning, that reads as a fuzzy blob erasing the icon — the halo
    // discs were removed in favour of the globe's post-process bloom.
    const globe = seriesFor('globe');
    expect(globe.some((s) => s.id === 'events__halo')).toBe(false);
    expect(globe.some((s) => s.id === 'events__halo_far')).toBe(false);
  });

  it('rings only the critical pins, and silently', () => {
    const layer = buildEventsLayer([
      event({ id: 'c', severity: 'critical', lon: 1, lat: 1 }),
      event({ id: 'l', severity: 'low', lon: 2, lat: 2 }),
    ]);
    const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode: 'globe' });
    const series = opt.series as unknown as Array<{ id: string; silent?: boolean; data: unknown[] }>;
    const ring = series.find((s) => s.id === 'events__critical_ring');
    expect(ring).toBeDefined();
    // One critical event in, one ring out — a low-severity pin gets none.
    expect(ring!.data).toHaveLength(1);
    // Silent, or it would steal the click from the pin underneath.
    expect(ring!.silent).toBe(true);
  });

  it('sends the category glyph as the symbol in BOTH projections', () => {
    // The glyph is what makes a conflict look like a blast. It must survive the
    // projection switch — echarts-gl resolves `path://` via the same helper.
    const layer = buildConflictLayer([event({ id: 'c1', lon: 5, lat: 5 })], () => {});
    for (const mode of ['2d', 'globe'] as const) {
      const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode });
      const series = opt.series as unknown as Array<{ id: string; symbol?: string }>;
      const core = series.find((s) => s.id === 'conflict')!;
      expect(core.symbol, `${mode} lost the glyph`).toBe(SYMBOL_PATHS.blast);
    }
  });

  it('keeps the ring styling scalar so echarts-gl cannot read a NaN size', () => {
    // echarts-gl reads itemStyle through getItemVisual, which does not invoke
    // callbacks for opacity — a function there yields invisible pins silently.
    const layer = buildEventsLayer([event({ id: 'c', severity: 'critical', lon: 1, lat: 1 })]);
    const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode: 'globe' });
    const series = opt.series as unknown as Array<{ id: string; itemStyle?: { opacity?: number } }>;
    const ring = series.find((s) => s.id === 'events__critical_ring')!;
    expect(typeof ring.itemStyle?.opacity).toBe('number');
  });
});

describe('map skin', () => {
  function geoFor(skin?: 'black' | 'glow') {
    const layer = buildEventsLayer([event({ id: 's1', lon: 10, lat: 10 })]);
    const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode: '2d', skin });
    return (opt as unknown as { geo: { itemStyle: { areaColor: string; borderColor: string; shadowBlur: number } } }).geo;
  }

  it('defaults to the blue lit-planet surface', () => {
    const geo = geoFor();
    // The glow surface is TRANSLUCENT blue, so the starfield reads through the
    // continents — that is what makes the flat map the same object as the globe.
    expect(geo.itemStyle.areaColor).toMatch(/^rgba\(/);
    expect(geo.itemStyle.areaColor).not.toBe('rgba(0,0,0,0)');
    expect(geo.itemStyle.borderColor).toContain('125,232,255');
    expect(geo.itemStyle.shadowBlur).toBeGreaterThan(0);
  });

  it('renders the plain terminal surface for the black skin', () => {
    const geo = geoFor('black');
    expect(geo.itemStyle.areaColor).toBe('#141416');
    // No bloom: the flat skin is deliberately glow-free.
    expect(geo.itemStyle.shadowBlur).toBe(0);
  });

  it('turns the globe aura and bloom off for the black skin', () => {
    const layer = buildEventsLayer([event({ id: 'g1', lon: 1, lat: 1 })]);
    const globeFor = (skin: 'black' | 'glow') => {
      const opt = buildMapOption({
        layers: [{ ...layer, enabled: true }],
        mode: 'globe',
        skin,
        globeGlowTexture: 'data:image/png;base64,AAAA',
      });
      return (opt as unknown as {
        globe: { layers: unknown[]; postEffect: { enable: boolean } };
      }).globe;
    };
    expect(globeFor('glow').postEffect.enable).toBe(true);
    expect(globeFor('glow').layers).toHaveLength(1);
    // The plain planet must not emit a coastline aura or run a post-process.
    expect(globeFor('black').postEffect.enable).toBe(false);
    expect(globeFor('black').layers).toHaveLength(0);
  });

  it('keeps the black globe grey, not near-black', () => {
    // A near-black texture under `lambert` lighting collapsed into an almost
    // featureless dark ball, so the plain skin uses mid-grey tones and enough
    // ambient to actually show them.
    const layer = buildEventsLayer([event({ id: 'g2', lon: 1, lat: 1 })]);
    const globeFor = (skin: 'black' | 'glow') => {
      const opt = buildMapOption({ layers: [{ ...layer, enabled: true }], mode: 'globe', skin });
      return (opt as unknown as {
        globe: { color: string; light: { ambient: { intensity: number } } };
      }).globe;
    };
    const black = globeFor('black');
    // #2a2d33 — mid-grey, and lighter than the blue skin's deep navy base.
    const grey = parseInt(black.color.slice(1), 16);
    const r = (grey >> 16) & 0xff;
    expect(r).toBeGreaterThan(0x20);
    expect(r).toBeLessThan(0x60);
    // Enough ambient that the grey does not collapse back to black.
    expect(black.light.ambient.intensity).toBeGreaterThanOrEqual(0.8);
  });
});

describe('severityColor', () => {
  it('maps every severity to the shared palette', () => {
    expect(severityColor('critical')).toBe('#ef4444');
    expect(severityColor('low')).toBe('#38bdf8');
  });
});

describe('hasDrawableBox', () => {
  // Regression: ECharts' geo View dereferences a null matrix when `setOption`
  // runs against a zero-size container (`Cannot read properties of null
  // (reading '0')`). An embedded map mounts before flex layout resolves its
  // height, so WorldMap must wait for a real box. Verified against the library:
  // 0x400 / 400x0 / 0x0 all throw, 1x1 and any real size are fine.
  it('rejects zero width or height', () => {
    expect(hasDrawableBox(0, 0)).toBe(false);
    expect(hasDrawableBox(0, 400)).toBe(false);
    expect(hasDrawableBox(400, 0)).toBe(false);
  });

  it('accepts any non-zero box', () => {
    expect(hasDrawableBox(1, 1)).toBe(true);
    expect(hasDrawableBox(320, 500)).toBe(true);
  });
});
