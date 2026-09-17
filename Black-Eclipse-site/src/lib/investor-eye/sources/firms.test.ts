import { describe, it, expect } from 'vitest';
import {
  parseFirmsCsv, clusterDetections, normalizeFireCluster, buildFireEvents,
  severityFromFrp, satelliteName, resolveFireCountry, FIRE_MIN_DETECTIONS,
  firmsSource, FIRMS_SOURCE_ID,
} from './firms';
import type { FireCluster } from './firms';
import type { RawEvent } from '../types';

// Real MODIS C6.1 header, so a column-order change in the parser is caught.
const HEADER = 'latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight';

function csv(rows: string[]): string {
  return [HEADER, ...rows].join('\n');
}

describe('parseFirmsCsv', () => {
  it('parses coordinates, FRP, confidence and builds a UTC timestamp', () => {
    const body = csv(['-19.93032,113.24658,312.03,1.37,1.16,2026-09-15,0039,T,52,6.1NRT,293.65,14.01,D']);
    const [d] = parseFirmsCsv(body);
    expect(d.lon).toBeCloseTo(113.24658, 4);
    expect(d.lat).toBeCloseTo(-19.93032, 4);
    expect(d.frp).toBe(14.01);
    expect(d.confidence).toBe(52);
    expect(d.satellite).toBe('Terra (MODIS)');
    expect(d.observedAt).toBe('2026-09-15T00:39:00.000Z');
  });

  it('pads a 3-digit acquisition time instead of inventing hours', () => {
    // FIRMS omits the leading zero before 01:00 ("35" = 00:35 UTC).
    const body = csv(['1,2,300,1,1,2026-09-15,35,A,84,6.1NRT,290,10,D']);
    expect(parseFirmsCsv(body)[0].observedAt).toBe('2026-09-15T00:35:00.000Z');
  });

  it('drops rows with a missing coordinate or timestamp rather than defaulting', () => {
    const body = csv([
      ',113.2,300,1,1,2026-09-15,0039,T,52,x,290,10,D',      // no latitude
      '1,2,300,1,1,not-a-date,0039,T,52,x,290,10,D',          // bad date
      '1,2,300,1,1,2026-09-15,,T,52,x,290,10,D',              // no time
    ]);
    expect(parseFirmsCsv(body)).toHaveLength(0);
  });

  it('rejects the (0,0) null-island sentinel', () => {
    const body = csv(['0,0,300,1,1,2026-09-15,0039,T,52,x,290,10,D']);
    expect(parseFirmsCsv(body)).toHaveLength(0);
  });

  it('maps letter confidence codes from VIIRS-style products', () => {
    const body = csv(['1,2,300,1,1,2026-09-15,0039,T,h,x,290,10,D']);
    expect(parseFirmsCsv(body)[0].confidence).toBe(90);
  });

  it('returns nothing for an empty or headerless body', () => {
    expect(parseFirmsCsv('')).toHaveLength(0);
    expect(parseFirmsCsv('a,b,c\n1,2,3')).toHaveLength(0);
  });
});

describe('clusterDetections', () => {
  const det = (lon: number, lat: number, frp: number, conf = 70, at = '2026-09-15T00:39:00.000Z') =>
    ({ lon, lat, frp, confidence: conf, satellite: 'Terra (MODIS)', observedAt: at });

  it('merges adjacent pixels into one cluster with summed FRP', () => {
    const clusters = clusterDetections([
      det(113.20, -19.90, 10),
      det(113.24, -19.93, 20),
      det(113.28, -19.95, 5),
    ]);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].count).toBe(3);
    expect(clusters[0].frpTotal).toBe(35);
    expect(clusters[0].frpMax).toBe(20);
  });

  it('keeps genuinely separate fires apart', () => {
    const clusters = clusterDetections([det(0, 0, 10), det(40, 30, 10)]);
    expect(clusters).toHaveLength(2);
  });

  it('tracks the most recent detection timestamp in a cell', () => {
    // Two pixels inside one 0.5° cell (1.1° and 1.2° across/down).
    const clusters = clusterDetections([
      det(1.1, 1.1, 10, 70, '2026-09-15T00:00:00.000Z'),
      det(1.2, 1.2, 10, 70, '2026-09-15T06:00:00.000Z'),
    ]);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].observedAt).toBe('2026-09-15T06:00:00.000Z');
  });

  it('corrects longitude cell width by latitude so polar fires are not fragmented', () => {
    // At 70°N a 0.5° longitude span is only ~19 km, vs ~55 km at the equator.
    // On an uncorrected 0.5° grid these two pixels straddle a cell boundary and
    // split; the cos(lat) correction keeps them one fire.
    const clusters = clusterDetections([
      det(20.6, 70, 10),
      det(21.1, 70, 10),
    ]);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].count).toBe(2);
  });
});

describe('severityFromFrp', () => {
  it('anchors thresholds to the published live distribution', () => {
    expect(severityFromFrp(50)).toBe('low');
    expect(severityFromFrp(300)).toBe('medium');
    expect(severityFromFrp(2000)).toBe('high');
    expect(severityFromFrp(9000)).toBe('critical');
  });
});

describe('satelliteName', () => {
  it('names the MODIS instruments and passes unknown codes through', () => {
    expect(satelliteName('T')).toBe('Terra (MODIS)');
    expect(satelliteName('A')).toBe('Aqua (MODIS)');
    expect(satelliteName('N20')).toBe('N20');
  });
});

describe('resolveFireCountry', () => {
  it('tags a fire near a known country', () => {
    // Central Indonesia.
    expect(resolveFireCountry(113.2, -1.5)?.iso2).toBe('ID');
  });

  it('resolves a point deep inside a large country, which centroid matching cannot', () => {
    // Eastern Siberia — thousands of km from Russia's centroid.
    expect(resolveFireCountry(115, 62)?.iso2).toBe('RU');
  });

  it('keeps a country the curated gazetteer lacks, rather than discarding a proven hit', () => {
    // Central Mozambique — in the boundary asset but not the country gazetteer.
    const moz = resolveFireCountry(35.5, -17.5);
    expect(moz?.iso2).toBe('MZ');
    expect(moz?.name).toBeTruthy();
  });

  it('leaves a remote ocean detection unlabelled rather than guessing', () => {
    // Deliberately mid-ocean so neither the polygon nor the centroid fallback hit.
    expect(resolveFireCountry(-140, -40)).toBeUndefined();
  });
});

describe('normalizeFireCluster', () => {
  const cluster: FireCluster = {
    lon: 113.2, lat: -1.5, count: 42, frpTotal: 1500, frpMax: 400,
    confidenceAvg: 75, satellite: 'Terra (MODIS)', observedAt: '2026-09-15T00:39:00.000Z',
  };

  it('states the detection count in the title so a cluster is not read as one ignition', () => {
    const e = normalizeFireCluster(cluster, '2026-09-15T01:00:00.000Z');
    expect(e.title).toContain('42 detections');
    expect(e.summary).toContain('42 satellite thermal detections');
  });

  it('uses the provider-stated category and exact coordinate', () => {
    const e = normalizeFireCluster(cluster, '2026-09-15T01:00:00.000Z');
    expect(e.eventType).toBe('natural_disaster');
    expect(e.category).toBe('fire');
    expect(e.geoMethod).toBe('provider');
    expect(e.lon).toBe(113.2);
    expect(e.lat).toBe(-1.5);
    expect(e.countries).toEqual(['ID']);
    expect(e.severity).toBe('high'); // 1500 MW
  });

  it('signs the cluster by its grid cell so identical titles cannot fuse', () => {
    const a = normalizeFireCluster(cluster, 'x');
    const b = normalizeFireCluster({ ...cluster, lon: 40, lat: 30 }, 'x');
    expect(a.clusterSignature).not.toBe(b.clusterSignature);
    expect(a.dedupKey).not.toBe(b.dedupKey);
  });

  it('does not use the shared feed URL as article identity', () => {
    // `dedupKeyFor` treats a source URL as article identity. A feed endpoint is
    // not an article — two different clusters would collapse into one event.
    const a = normalizeFireCluster(cluster, 'x');
    const b = normalizeFireCluster({ ...cluster, lon: 40, lat: 30 }, 'x');
    expect(a.sources[0].url).toBeUndefined();
    expect(a.sources[0].id).toBe(FIRMS_SOURCE_ID);
    expect(b.dedupKey).not.toBe(a.dedupKey);
  });
});

describe('buildFireEvents', () => {
  function records(rows: string[]): RawEvent[] {
    return [{ sourceId: FIRMS_SOURCE_ID, sourceName: 'NASA FIRMS', raw: { csv: csv(rows) }, retrievedAt: '2026-09-15T01:00:00.000Z' }];
  }

  it('drops clusters below the minimum detection count', () => {
    // All nine pixels fall in one cell; nine is below the threshold of ten.
    const rows = Array.from({ length: FIRE_MIN_DETECTIONS - 1 }, (_, i) =>
      `-1.50,${(113.2 + i * 0.01).toFixed(4)},300,1,1,2026-09-15,0039,T,80,x,290,${10 + i},D`,
    );
    expect(buildFireEvents(records(rows))).toHaveLength(0);
  });

  it('emits one event per qualifying cluster', () => {
    const rows = Array.from({ length: FIRE_MIN_DETECTIONS + 5 }, (_, i) =>
      `-1.50,${(113.2 + i * 0.01).toFixed(4)},300,1,1,2026-09-15,0039,T,80,x,290,${10 + i},D`,
    );
    const events = buildFireEvents(records(rows));
    expect(events).toHaveLength(1);
    expect(events[0].category).toBe('fire');
    expect(events[0].primarySource).toBe(FIRMS_SOURCE_ID);
  });

  it('returns nothing when no record carries a CSV body', () => {
    expect(buildFireEvents([{ sourceId: 'firms', sourceName: 'x', raw: {}, retrievedAt: 'x' }])).toHaveLength(0);
  });
});

describe('firmsSource contract', () => {
  it('is keyless and configured out of the box', () => {
    expect(firmsSource.requiresCredentials).toBe(false);
    expect(firmsSource.isConfigured()).toBe(true);
    expect(firmsSource.capabilities).toContain('NATURAL_EVENTS');
  });
});
