// ── Investor Eye — globe sizing & country labels ─────────────────────────────
// Regression cover for two map presentation fixes:
//   1. the globe camera distance is derived from the container box so the
//      sphere fills the view (the old hard-coded pair rendered it ~65%),
//   2. country names render in BOTH projections via a shared label series.

import { describe, it, expect } from 'vitest';
import { buildMapOption, buildCountryOutlineSeries, globeViewDistance, GLOBE_RADIUS } from './map-echarts';
import { buildEventsLayer } from './layers';
import type { NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1', dedupKey: 'e1', title: 'Event', eventType: 'conflict', severity: 'high',
    channels: [], commodities: [], sectors: [], securities: [], countries: ['TR'],
    lon: 30, lat: 39, confidence: 0.5, sourceCount: 1, sources: [],
    primarySource: 'gdelt', publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

describe('globeViewDistance', () => {
  it('is positive and finite for a real box', () => {
    const d = globeViewDistance(1200, 550);
    expect(Number.isFinite(d)).toBe(true);
    expect(d).toBeGreaterThan(0);
  });

  it('is resolution-independent: framing depends on aspect ratio, not pixel size', () => {
    // A perspective camera fills the same proportion of any box with the same
    // aspect ratio, so doubling the box must not change the distance. This is
    // what makes the globe fill the map on both a phone and a 4K monitor.
    expect(globeViewDistance(600, 300)).toBeCloseTo(globeViewDistance(1200, 600), 6);
  });

  it('pulls the camera back for a taller (portrait) box', () => {
    // A sphere is limited by the SHORTER viewport dimension; a narrow box shrinks
    // that limiting dimension, so the camera must move back to keep the fill.
    expect(globeViewDistance(400, 900)).toBeGreaterThan(globeViewDistance(900, 900));
  });

  it('returns a usable default when the box is not laid out yet', () => {
    const d = globeViewDistance(0, 0);
    expect(Number.isFinite(d)).toBe(true);
    expect(d).toBeGreaterThan(0);
  });

  it('never returns a distance that would place the camera inside the sphere', () => {
    for (const [w, h] of [[320, 200], [1920, 1080], [800, 800], [400, 900]] as const) {
      const d = globeViewDistance(w, h);
      expect(d).toBeGreaterThan(GLOBE_RADIUS * 0.2);
    }
  });
});

describe('country labels', () => {
  function opts(mode: '2d' | 'globe', extra: Record<string, unknown> = {}) {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    return buildMapOption({ layers: [layer], mode, width: 1000, height: 600, ...extra });
  }

  function labelSeries(mode: '2d' | 'globe') {
    const series = opts(mode).series as unknown as Array<{
      id: string; type: string; label?: { show?: boolean; formatter?: (p: { name?: string }) => string };
      data: Array<{ name?: string; value: number[] }>;
    }>;
    return series.find((s) => s.id === 'country-labels');
  }

  it('emits a country-label series in 2D and on the globe', () => {
    expect(labelSeries('2d')?.type).toBe('scatter');
    expect(labelSeries('globe')?.type).toBe('scatter3D');
  });

  it('is always on by default', () => {
    expect(labelSeries('2d')?.label?.show).toBe(true);
  });

  it('can be turned off', () => {
    const series = opts('2d', { showCountryLabels: false }).series as unknown as Array<{ id: string }>;
    expect(series.some((s) => s.id === 'country-labels')).toBe(false);
  });

  it('formats the label from the data item name', () => {
    const fmt = labelSeries('2d')?.label?.formatter;
    expect(fmt?.({ name: 'France' })).toBe('France');
    expect(fmt?.({})).toBe('');
  });

  it('carries exactly [lon, lat] on the globe (no altitude spike)', () => {
    expect(labelSeries('globe')?.data[0].value).toHaveLength(2);
  });

  it('does not capture clicks meant for the event pins', () => {
    const series = opts('2d').series as unknown as Array<{ id: string; silent?: boolean }>;
    expect(series.find((s) => s.id === 'country-labels')?.silent).toBe(true);
  });

  it('is SMALL and light, with a soft shadow rather than a hard stroke', () => {
    // A hard pixel outline on 9px text smears the glyphs; a shadow separates the
    // name from the land without deforming it.
    const series = opts('2d').series as unknown as Array<{
      id: string;
      label?: { fontSize?: number; textBorderWidth?: number; textShadowBlur?: number; fontFamily?: string };
    }>;
    const label = series.find((s) => s.id === 'country-labels')?.label;
    expect(label?.fontSize).toBeLessThanOrEqual(10);
    expect(label?.textBorderWidth ?? 0).toBe(0);
    expect(label?.textShadowBlur).toBeGreaterThan(0);
    expect(label?.fontFamily).toContain('Inter');
  });
});

describe('globe hovered-country outline', () => {
  it('emits an (empty) outline series in globe mode so it can be updated in place', () => {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: 'globe' });
    const series = opt.series as unknown as Array<{ id: string; type: string; data: unknown[] }>;
    const outline = series.find((s) => s.id === 'country-outline');
    expect(outline).toBeDefined();
    expect(outline!.type).toBe('lines3D');
    expect(outline!.data).toHaveLength(0);
  });

  it('does NOT emit the outline in 2D (geo highlights natively there)', () => {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: '2d' });
    const series = opt.series as unknown as Array<{ id: string }>;
    expect(series.some((s) => s.id === 'country-outline')).toBe(false);
  });

  it('draws supplied rings as closed polylines', () => {
    const ring: Array<[number, number]> = [[0, 0], [10, 0], [10, 10], [0, 0]];
    const s = buildCountryOutlineSeries([ring]) as { polyline?: boolean; data: Array<{ coords: [number, number][] }> };
    expect(s.polyline).toBe(true);
    expect(s.data[0].coords).toEqual(ring);
  });

  it('ignores degenerate rings (fewer than 3 points)', () => {
    const s = buildCountryOutlineSeries([[[0, 0], [1, 1]]]) as { data: unknown[] };
    expect(s.data).toHaveLength(0);
  });
});
