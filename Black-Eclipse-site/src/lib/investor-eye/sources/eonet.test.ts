import { describe, it, expect } from 'vitest';
import {
  mapEonetCategory, pickLatestGeometry, severityFromWindKnots, eonetSeverity,
  normalizeEonetEvent, buildEonetEvents, daysForHours, EONET_SOURCE_ID,
} from './eonet';
import type { RawEvent } from '../types';

const retrievedAt = '2026-09-16T12:00:00.000Z';

describe('mapEonetCategory', () => {
  it('folds overlapping hazards onto the shared vocabulary', () => {
    expect(mapEonetCategory('wildfires')).toBe('fire');
    expect(mapEonetCategory('earthquakes')).toBe('earthquake');
    expect(mapEonetCategory('severeStorms')).toBe('storm');
    expect(mapEonetCategory('floods')).toBe('flood');
    expect(mapEonetCategory('volcanoes')).toBe('volcano');
  });

  it('lower-cases an unknown category rather than dropping it', () => {
    expect(mapEonetCategory('SomethingNew')).toBe('somethingnew');
    expect(mapEonetCategory(undefined)).toBeUndefined();
  });
});

describe('pickLatestGeometry', () => {
  it('chooses the most recent observation, not the first', () => {
    const p = pickLatestGeometry([
      { type: 'Point', coordinates: [10, 10], date: '2026-09-10T00:00:00Z' },
      { type: 'Point', coordinates: [30, 30], date: '2026-09-15T00:00:00Z' },
    ]);
    expect(p).toEqual({ lon: 30, lat: 30, at: '2026-09-15T00:00:00Z' });
  });

  it('reduces a polygon to a representative centroid', () => {
    const p = pickLatestGeometry([
      {
        type: 'Polygon',
        date: '2026-09-15T00:00:00Z',
        // A 2x2 square from (0,0) to (2,2) → centroid (1,1).
        coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
      },
    ]);
    expect(p?.lon).toBeCloseTo(1, 6);
    expect(p?.lat).toBeCloseTo(1, 6);
  });

  it('rejects a null-island coordinate instead of plotting it', () => {
    expect(pickLatestGeometry([{ type: 'Point', coordinates: [0, 0] }])).toBeNull();
  });

  it('returns null when geometry is missing', () => {
    expect(pickLatestGeometry([])).toBeNull();
    expect(pickLatestGeometry(undefined)).toBeNull();
  });
});

describe('severityFromWindKnots', () => {
  it('maps tropical-cyclone bands to severity', () => {
    expect(severityFromWindKnots(120, 'kts')).toBe('critical');
    expect(severityFromWindKnots(70, 'kts')).toBe('high');
    expect(severityFromWindKnots(40, 'kts')).toBe('medium');
    expect(severityFromWindKnots(20, 'kts')).toBe('low');
  });

  it('normalizes mph and m/s into knots', () => {
    // 100 mph ≈ 87 kt → high.
    expect(severityFromWindKnots(100, 'mph')).toBe('high');
    // 60 m/s ≈ 117 kt → critical.
    expect(severityFromWindKnots(60, 'm/s')).toBe('critical');
  });

  it('refuses to scale an unknown unit', () => {
    expect(severityFromWindKnots(500, 'meters')).toBeUndefined();
  });
});

describe('eonetSeverity', () => {
  it('uses the earthquake magnitude scale for earthquakes', () => {
    expect(eonetSeverity('earthquake', 7.5, 'm', 'earthquake')).toBe('critical');
    expect(eonetSeverity('earthquake', 3.0, 'm', 'earthquake')).toBe('low');
  });

  it('uses the wind scale for storms', () => {
    expect(eonetSeverity('storm', 110, 'kts', 'hurricane')).toBe('critical');
  });

  it('falls back to the text lexicon when no usable magnitude exists', () => {
    expect(eonetSeverity('flood', null, null, 'catastrophic flooding')).toBe('critical');
    // A storm value in an unknown unit must not be mis-scaled as an earthquake.
    expect(eonetSeverity('storm', 500, 'meters', 'tropical storm')).not.toBe('critical');
  });
});

describe('daysForHours', () => {
  it('maps the window to a bounded day count', () => {
    expect(daysForHours(6)).toBe(1);
    expect(daysForHours(48)).toBe(2);
    expect(daysForHours(24 * 100)).toBe(20);
  });
});

describe('normalizeEonetEvent', () => {
  const event = {
    id: 'EONET_9001',
    title: 'Tropical Cyclone Gaemi',
    link: 'https://eonet.gsfc.nasa.gov/api/v3/events/EONET_9001',
    categories: [{ id: 'severeStorms', title: 'Severe Storms' }],
    sources: [
      { id: 'JTWC', source: 'Joint Typhoon Warning Center', url: 'https://metoc.npmoc.navy.mil/jtwc.html' },
      { id: 'GDACS', source: 'GDACS', url: 'https://www.gdacs.org/' },
    ],
    geometry: [
      { type: 'Point', coordinates: [134.5, 15.0], date: '2026-09-15T00:00:00Z', magnitudeValue: 110, magnitudeUnit: 'kts' },
      { type: 'Point', coordinates: [130.0, 18.0], date: '2026-09-16T06:00:00Z', magnitudeValue: 120, magnitudeUnit: 'kts' },
    ],
  };

  it('builds a normalized hazard event with a stable provider identity', () => {
    const e = normalizeEonetEvent(event, retrievedAt);
    expect(e).not.toBeNull();
    expect(e!.eventType).toBe('natural_disaster');
    expect(e!.category).toBe('storm');
    expect(e!.primarySource).toBe(EONET_SOURCE_ID);
    expect(e!.clusterSignature).toBe('eonet:EONET_9001');
    // Latest geometry wins.
    expect(e!.lon).toBe(130.0);
    expect(e!.lat).toBe(18.0);
    expect(e!.severity).toBe('critical'); // 120 kt
    expect(e!.dedupKey).toHaveLength(40);
  });

  it('counts the primary plus each citing agency as corroboration', () => {
    const e = normalizeEonetEvent(event, retrievedAt)!;
    expect(e.sourceCount).toBe(3);
    expect(e.sources[0].id).toBe('eonet');
    expect(e.sources.map((s) => s.name)).toContain('Joint Typhoon Warning Center');
  });

  it('carries only the EONET event link as a source URL (never an agency URL)', () => {
    const e = normalizeEonetEvent(event, retrievedAt)!;
    const urls = e.sources.map((s) => s.url).filter(Boolean);
    expect(urls).toEqual(['https://eonet.gsfc.nasa.gov/api/v3/events/EONET_9001']);
  });

  it('returns null without an id or without geometry', () => {
    expect(normalizeEonetEvent({ title: 'x', geometry: [{ type: 'Point', coordinates: [1, 1] }] }, retrievedAt)).toBeNull();
    expect(normalizeEonetEvent({ id: 'E1', title: 'x', geometry: [] }, retrievedAt)).toBeNull();
  });

  it('never invents a headline — the title is the provider title', () => {
    const e = normalizeEonetEvent(event, retrievedAt)!;
    expect(e.title).toBe('Tropical Cyclone Gaemi');
  });
});

describe('buildEonetEvents', () => {
  it('normalizes a raw batch and drops unusable records', () => {
    const records: RawEvent[] = [
      {
        sourceId: 'eonet', sourceName: 'NASA EONET', retrievedAt,
        raw: { id: 'E1', title: 'Wildfire X', categories: [{ id: 'wildfires' }], geometry: [{ type: 'Point', coordinates: [134, -25], date: retrievedAt }] },
      },
      { sourceId: 'eonet', sourceName: 'NASA EONET', retrievedAt, raw: { id: '', title: 'no id' } },
    ];
    const events = buildEonetEvents(records);
    expect(events).toHaveLength(1);
    expect(events[0].category).toBe('fire');
    // (134, -25) is deep inside Australia.
    expect(events[0].countries).toContain('AU');
  });
});
