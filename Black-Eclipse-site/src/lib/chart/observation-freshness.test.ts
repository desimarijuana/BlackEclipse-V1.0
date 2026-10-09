import { describe, it, expect } from 'vitest';
import {
  assessFreshness,
  lastBarTimeMs,
  observationMeta,
  ruleForInterval,
  freshnessLabel,
  describeSeriesSource,
} from './observation-freshness';

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const NOW = 1_700_000_000_000;

describe('ruleForInterval', () => {
  it('gives intraday intervals tighter windows than daily', () => {
    expect(ruleForInterval('1m').live).toBeLessThan(ruleForInterval('1d').live);
    expect(ruleForInterval('1h').live).toBeLessThan(ruleForInterval('1wk').live);
  });
  it('falls back to the daily rule for unknown intervals', () => {
    expect(ruleForInterval('bogus')).toEqual(ruleForInterval('1d'));
  });
});

describe('assessFreshness', () => {
  it('never calls an unknown time live', () => {
    const r = assessFreshness(null, '1d', NOW);
    expect(r.freshness).toBe('unknown');
    expect(r.stale).toBe(true);
  });

  it('marks a same-session daily bar live', () => {
    const r = assessFreshness(NOW - 2 * HOUR, '1d', NOW);
    expect(r.freshness).toBe('live');
    expect(r.stale).toBe(false);
  });

  it('marks a week-old daily bar stale', () => {
    const r = assessFreshness(NOW - 20 * DAY, '1d', NOW);
    expect(r.freshness).toBe('stale');
    expect(r.stale).toBe(true);
  });

  it('ages a 1-minute bar within minutes', () => {
    const fresh = assessFreshness(NOW - 30_000, '1m', NOW);
    expect(fresh.freshness).toBe('live');
    const stale = assessFreshness(NOW - 20 * MIN, '1m', NOW);
    expect(stale.freshness).toBe('stale');
  });

  it('treats a future timestamp as current, not stale (clock skew)', () => {
    const r = assessFreshness(NOW + 5 * MIN, '1d', NOW);
    expect(r.freshness).toBe('live');
    expect(r.ageMs).toBe(0);
  });
});

describe('lastBarTimeMs', () => {
  it('prefers an explicit epoch time', () => {
    expect(lastBarTimeMs([{ date: '2020-01-01', time: NOW }])).toBe(NOW);
  });
  it('parses a date-only bar as UTC midnight', () => {
    expect(lastBarTimeMs([{ date: '2020-01-01' }])).toBe(Date.parse('2020-01-01T00:00:00Z'));
  });
  it('returns null for an empty series', () => {
    expect(lastBarTimeMs([])).toBeNull();
    expect(lastBarTimeMs(null)).toBeNull();
  });
});

describe('observationMeta', () => {
  it('stamps retrievedAt and derives observationTime from the newest bar', () => {
    const meta = observationMeta([{ date: '2026-09-16' }], '1d', NOW);
    expect(meta.retrievedAt).toBe(new Date(NOW).toISOString());
    expect(meta.observationTime).toBe('2026-09-16T00:00:00.000Z');
  });
  it('reports unavailable-quality detail as unknown when no bars', () => {
    const meta = observationMeta([], '1d', NOW);
    expect(meta.observationTime).toBeNull();
    expect(meta.freshness).toBe('unknown');
    expect(meta.stale).toBe(true);
  });
});

describe('freshnessLabel', () => {
  it('labels every state', () => {
    expect(freshnessLabel('live')).toBe('Live');
    expect(freshnessLabel('stale')).toBe('Stale');
    expect(freshnessLabel('unknown')).toBe('Unknown');
  });
});

describe('describeSeriesSource', () => {
  it('never calls a stale observation live', () => {
    expect(describeSeriesSource('snapshot', 'stale', '2026-01-02T00:00:00.000Z'))
      .toBe('stale · as of 2026-01-02');
    expect(describeSeriesSource('yfinance', 'stale', null)).toBe('stale');
  });
  it('labels a fresh provider feed as live', () => {
    expect(describeSeriesSource('yfinance', 'live', null)).toBe('live · Yahoo Finance');
    expect(describeSeriesSource('psx', 'live', null)).toBe('live · PSX');
  });
  it('shows the snapshot as-of date', () => {
    expect(describeSeriesSource('snapshot', 'unknown', '2025-12-31T00:00:00.000Z'))
      .toBe('delayed · as of 2025-12-31');
  });
  it('returns empty for no source', () => {
    expect(describeSeriesSource('none', 'unavailable', null)).toBe('');
    expect(describeSeriesSource(undefined, undefined, undefined)).toBe('');
  });
});
