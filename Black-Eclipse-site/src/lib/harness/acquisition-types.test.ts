import { describe, expect, it } from 'vitest';
import { coerceAcquisitionManifest } from './acquisition-types';

const manifest = {
  purpose: 'two years for the watchlist',
  collectedAt: '2026-10-18T12:00:00Z',
  sources: [
    {
      id: 'prices_daily',
      label: 'Daily price history',
      window: { from: '2024-01-02', to: '2024-01-03' },
      rows: 4,
      file: 'prices_daily_20261018-120000.csv',
      complete: true,
      stoppedReason: null,
      licence: 'vendor terms — see attribution',
      attribution: 'Yahoo Finance (unofficial endpoint)',
    },
  ],
};

describe('coerceAcquisitionManifest', () => {
  it('narrows a complete manifest', () => {
    const data = coerceAcquisitionManifest(manifest);
    expect(data).not.toBeNull();
    expect(data?.purpose).toBe('two years for the watchlist');
    expect(data?.sources).toHaveLength(1);
    expect(data?.sources[0]).toMatchObject({
      id: 'prices_daily',
      label: 'Daily price history',
      windowFrom: '2024-01-02',
      windowTo: '2024-01-03',
      rows: 4,
      complete: true,
      licence: 'vendor terms — see attribution',
      attribution: 'Yahoo Finance (unofficial endpoint)',
    });
  });

  it('a missing or non-true completeness reads PARTIAL — never rounded up', () => {
    const noFlag = coerceAcquisitionManifest({
      sources: [{ id: 'x', label: 'X', complete: 'yes' }],
    });
    expect(noFlag?.sources[0].complete).toBe(false);
  });

  it('an unknown row count is null, not a fabricated 0', () => {
    const data = coerceAcquisitionManifest({ sources: [{ id: 'x' }] });
    expect(data?.sources[0].rows).toBeNull();
    expect(data?.sources[0].label).toBe('x');
  });

  it('rejects blobs that cannot render honestly', () => {
    expect(coerceAcquisitionManifest(null)).toBeNull();
    expect(coerceAcquisitionManifest([])).toBeNull();
    expect(coerceAcquisitionManifest({})).toBeNull();
    expect(coerceAcquisitionManifest({ sources: [] })).toBeNull();
    expect(coerceAcquisitionManifest({ sources: [{ label: 'no id' }] })).toBeNull();
  });
});
