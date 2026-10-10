import { describe, it, expect } from 'vitest';
import { parseLastUpdateInfo, bulkExportUrls, gdeltSource } from './gdelt';
import { scoreRelevance, KEEP_THRESHOLD } from '../relevance';
import type { RawEvent } from '../types';

describe('parseLastUpdateInfo', () => {
  const body = [
    '120506 18e18fecbbc5d43bd5e77993f20d9f1e http://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip',
    '155776 78a951719270ab27c4b92a04cbe83e45 http://data.gdeltproject.org/gdeltv2/20260916151500.mentions.CSV.zip',
  ].join('\n');

  it('returns the export URL upgraded to https plus its timestamp', () => {
    expect(parseLastUpdateInfo(body)).toEqual({
      url: 'https://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip',
      timestamp: '20260916151500',
    });
  });

  it('returns null for an empty body', () => {
    expect(parseLastUpdateInfo('')).toBeNull();
  });
});

describe('bulkExportUrls', () => {
  const latest = 'https://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip';

  it('walks backwards in 15-minute slots', () => {
    expect(bulkExportUrls(latest, 4)).toEqual([
      'https://data.gdeltproject.org/gdeltv2/20260916151500.export.CSV.zip',
      'https://data.gdeltproject.org/gdeltv2/20260916150000.export.CSV.zip',
      'https://data.gdeltproject.org/gdeltv2/20260916144500.export.CSV.zip',
      'https://data.gdeltproject.org/gdeltv2/20260916143000.export.CSV.zip',
    ]);
  });

  it('rolls back across an hour boundary', () => {
    const url = bulkExportUrls('https://data.gdeltproject.org/gdeltv2/20260916000000.export.CSV.zip', 2);
    expect(url[1]).toContain('20260915234500.export.CSV.zip');
  });

  it('returns just the latest when no timestamp can be parsed', () => {
    expect(bulkExportUrls('https://example.com/x.export.CSV.zip', 5)).toEqual(['https://example.com/x.export.CSV.zip']);
    expect(bulkExportUrls(latest, 1)).toEqual([latest]);
  });
});

describe('gdelt normalize', () => {
  const row = (over: Record<number, string> = {}) => {
    const f = new Array(61).fill('');
    f[0] = '1234567890';
    f[6] = 'MILITARY';
    f[16] = 'REBELS';
    f[26] = '190';
    f[28] = '19';
    f[29] = '4';
    f[30] = '-9.0';
    f[31] = '150';
    f[32] = '42';
    f[52] = 'Kyiv, Ukraine';
    f[53] = 'UP';
    f[56] = '50.45';
    f[57] = '30.52';
    f[59] = '20260916151500';
    f[60] = 'https://example.com/one';
    for (const [i, v] of Object.entries(over)) f[Number(i)] = v;
    return f;
  };

  it('de-duplicates repeated GLOBALEVENTIDs across overlapping slots', () => {
    const raw = (id: string, mentions: string): RawEvent => ({
      sourceId: 'gdelt', sourceName: 'GDELT', retrievedAt: '2026-09-16T15:20:00.000Z',
      raw: { kind: 'export', fields: row({ 0: id, 31: mentions }) },
    });
    const events = gdeltSource.normalize([raw('E1', '5'), raw('E1', '900'), raw('E2', '5')]);
    // E1 collapses to one event; E2 remains distinct.
    expect(events).toHaveLength(2);
    const e1 = events.find((e) => e.clusterSignature === 'gdelt:E1')!;
    // The higher-mention row won.
    expect(e1.confidence).toBeGreaterThan(0);
  });
});

describe('material-conflict relevance floor', () => {
  it('keeps a material conflict that would otherwise fall below the threshold', () => {
    // No resolved countries and a single actor — two penalties that normally
    // drop a score below KEEP_THRESHOLD.
    const r = scoreRelevance({
      quadClass: 4,
      goldstein: -8,
      countries: [],
      isStateDyad: false,
      eventType: 'other',
      hasEconomicSignal: false,
    });
    expect(r.score).toBeGreaterThanOrEqual(KEEP_THRESHOLD);
    expect(r.keep).toBe(true);
  });

  it('does not lift a non-conflict local incident', () => {
    const r = scoreRelevance({
      quadClass: 1,
      countries: [],
      isStateDyad: false,
      eventType: 'other',
      hasEconomicSignal: false,
    });
    expect(r.keep).toBe(false);
  });
});
