import { describe, it, expect } from 'vitest';
import { buildMapOption } from './map-echarts';
import { buildEventsLayer, buildConflictLayer } from './layers';
import type { NormalizedEvent } from './types';

// The globe showed no pins. These tests assert the globe series actually carry
// data, because a silently-empty series renders an empty sphere with no error.

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1', dedupKey: 'e1', title: 'Event', eventType: 'conflict', severity: 'high',
    channels: [], commodities: [], sectors: [], securities: [], countries: ['IR'],
    lon: 51.39, lat: 35.69, confidence: 0.8, sourceCount: 1, sources: [],
    primarySource: 'gdelt', publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

describe('globe series data', () => {
  it('emits scatter3D series WITH data in globe mode', () => {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: 'globe', globeTexture: 'data:image/png;base64,AAAA' });
    const series = (opt.series as unknown as Array<{ id: string; type: string; data: unknown[] }>)
      .filter((s) => s.id === 'events');
    expect(series).toHaveLength(1);
    expect(series[0].type).toBe('scatter3D');
    expect(series[0].data.length).toBeGreaterThan(0);
  });

  it('globe points carry exactly [lon, lat] (no altitude slot)', () => {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: 'globe' });
    const s = (opt.series as unknown as Array<{ id: string; data: Array<{ value: number[] }> }>)
      .find((x) => x.id === 'events')!;
    expect(s.data[0].value).toHaveLength(2);
    expect(s.data[0].value[0]).toBeCloseTo(51.39, 2);
  });

  it('keeps the category layers populated in globe mode too', () => {
    const layer = { ...buildConflictLayer([event()], () => {}), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: 'globe' });
    const s = (opt.series as unknown as Array<{ id: string; data: unknown[] }>).find((x) => x.id === 'conflict')!;
    expect(s.data.length).toBeGreaterThan(0);
  });

  it('2D mode still emits its own series with data', () => {
    const layer = { ...buildEventsLayer([event()]), enabled: true };
    const opt = buildMapOption({ layers: [layer], mode: '2d' });
    const s = (opt.series as unknown as Array<{ id: string; type: string; data: unknown[] }>)
      .find((x) => x.id === 'events')!;
    expect(['scatter', 'effectScatter']).toContain(s.type);
    expect(s.data.length).toBeGreaterThan(0);
  });
});
