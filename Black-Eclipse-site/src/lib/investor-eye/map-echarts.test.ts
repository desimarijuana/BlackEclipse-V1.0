// ── Investor Eye — map adapter contract ──────────────────────────────────────
// Regression cover for the ECharts boundary. These bugs were invisible to
// `tsc` because the payload is `unknown` at the library edge, and they only
// surfaced as runtime crashes in the browser.

import { describe, it, expect } from 'vitest';
import { buildMapOption, unwrapDatum } from './map-echarts';
import { buildConflictLayer, buildEventsLayer, severityColor } from './layers';
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

describe('severityColor', () => {
  it('maps every severity to the shared palette', () => {
    expect(severityColor('critical')).toBe('#ef4444');
    expect(severityColor('low')).toBe('#38bdf8');
  });
});
