import { describe, it, expect } from 'vitest';
import { clusterEvents, shouldCluster, mergeEvents, tokenSimilarity, significantTokens, confidenceOf } from './cluster';
import { dedupKeyFor, timeBucket } from './dedup';
import type { NormalizedEvent } from './types';

function makeEvent(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  const key = overrides.dedupKey ?? 'k';
  // Each fixture defaults to a DISTINCT source, so merging genuinely increases
  // sourceCount (the merge dedupes by source id, which is correct behavior).
  return {
    dedupKey: key,
    title: 'Trade restrictions announced on semiconductors',
    eventType: 'trade',
    severity: 'medium',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['CN'],
    lon: 100,
    lat: 30,
    confidence: 0.5,
    sourceCount: 1,
    sources: [{ id: `src-${key}`, name: `Source ${key}` }],
    primarySource: 'gdelt',
    publishedAt: '2026-09-15T10:00:00.000Z',
    ...overrides,
  };
}

describe('significantTokens / tokenSimilarity', () => {
  it('drops stop words and short tokens', () => {
    const tokens = significantTokens('The war in the region is a big deal');
    expect(tokens.has('the')).toBe(false);
    expect(tokens.has('war')).toBe(true);
    expect(tokens.has('big')).toBe(true);
  });

  it('scores identical sets as 1 and disjoint as 0', () => {
    expect(tokenSimilarity(new Set(['a', 'b']), new Set(['a', 'b']))).toBe(1);
    expect(tokenSimilarity(new Set(['a']), new Set(['b']))).toBe(0);
    expect(tokenSimilarity(new Set(), new Set(['a']))).toBe(0);
  });
});

describe('shouldCluster', () => {
  it('merges same-type, same-country, close-in-time, similar-title events', () => {
    const a = makeEvent();
    const b = makeEvent({ title: 'Trade restrictions announced on chips', publishedAt: '2026-09-15T12:00:00.000Z' });
    expect(shouldCluster(a, b)).toBe(true);
  });

  it('refuses different event types', () => {
    expect(shouldCluster(makeEvent(), makeEvent({ eventType: 'conflict' }))).toBe(false);
  });

  it('refuses events far apart in time', () => {
    expect(shouldCluster(makeEvent(), makeEvent({ publishedAt: '2026-09-18T10:00:00.000Z' }))).toBe(false);
  });

  it('refuses unrelated titles in different countries', () => {
    const a = makeEvent({ title: 'Election results announced', countries: ['FR'], eventType: 'election' });
    const b = makeEvent({ title: 'Flooding in coastal towns', countries: ['PH'], eventType: 'election' });
    expect(shouldCluster(a, b)).toBe(false);
  });
});

describe('mergeEvents', () => {
  it('combines sources, countries and channels without duplicates', () => {
    const a = makeEvent({ sources: [{ id: 'a', name: 'A' }], countries: ['CN'], channels: ['Trade & Tariffs'] });
    const b = makeEvent({ sources: [{ id: 'b', name: 'B' }], countries: ['CN', 'US'], channels: ['Semiconductors'] });
    const merged = mergeEvents(a, b);
    expect(merged.sourceCount).toBe(2);
    expect(merged.countries.sort()).toEqual(['CN', 'US']);
    expect(merged.channels).toContain('Semiconductors');
    expect(merged.channels).toContain('Trade & Tariffs');
  });

  it('keeps the earliest timestamp', () => {
    const a = makeEvent({ publishedAt: '2026-09-15T10:00:00.000Z' });
    const b = makeEvent({ publishedAt: '2026-09-15T08:00:00.000Z' });
    expect(mergeEvents(a, b).publishedAt).toBe('2026-09-15T08:00:00.000Z');
  });
});

describe('clusterEvents', () => {
  it('collapses duplicate reports into one event', () => {
    const events = [
      makeEvent({ dedupKey: 'a', title: 'Trade restrictions announced on semiconductors' }),
      makeEvent({ dedupKey: 'b', title: 'Trade restrictions announced on semiconductor exports' }),
      makeEvent({ dedupKey: 'c', title: 'Trade restrictions announced for semiconductors' }),
    ];
    const clustered = clusterEvents(events);
    expect(clustered).toHaveLength(1);
    expect(clustered[0].sourceCount).toBe(3);
  });

  it('keeps genuinely different events apart', () => {
    const events = [
      makeEvent({ dedupKey: 'a', eventType: 'trade', countries: ['CN'] }),
      makeEvent({ dedupKey: 'b', eventType: 'conflict', title: 'Missile strikes hit port', countries: ['UA'] }),
    ];
    expect(clusterEvents(events)).toHaveLength(2);
  });

  it('is deterministic for identical input', () => {
    const events = [makeEvent({ dedupKey: 'a' }), makeEvent({ dedupKey: 'b', sources: [{ id: 'b', name: 'B' }] })];
    const first = clusterEvents(events).map((e) => e.dedupKey);
    const second = clusterEvents(events).map((e) => e.dedupKey);
    expect(first).toEqual(second);
  });
});

describe('dedupKeyFor', () => {
  it('is stable for the same identity', () => {
    const e = makeEvent();
    expect(dedupKeyFor(e)).toBe(dedupKeyFor(e));
  });

  it('differs across types, countries or windows', () => {
    const base = makeEvent();
    expect(dedupKeyFor(base)).not.toBe(dedupKeyFor({ ...base, eventType: 'conflict' }));
    expect(dedupKeyFor(base)).not.toBe(dedupKeyFor({ ...base, countries: ['US'] }));
    expect(dedupKeyFor(base)).not.toBe(
      dedupKeyFor({ ...base, publishedAt: '2026-09-15T23:00:00.000Z' }),
    );
  });

  it('timeBucket groups within a window', () => {
    expect(timeBucket('2026-09-15T10:00:00.000Z', 6)).toBe(timeBucket('2026-09-15T11:00:00.000Z', 6));
  });
});

describe('confidenceOf', () => {
  it('is bounded 0..1', () => {
    expect(confidenceOf(makeEvent())).toBeGreaterThan(0);
    expect(confidenceOf(makeEvent())).toBeLessThanOrEqual(1);
  });

  it('rises with corroborating sources', () => {
    const one = confidenceOf(makeEvent({ sourceCount: 1 }));
    const five = confidenceOf(makeEvent({ sourceCount: 5, sources: Array(5).fill({ id: 's', name: 'S' }) }));
    expect(five).toBeGreaterThan(one);
  });

  it('is lower when there is no location', () => {
    const noLocation = confidenceOf(makeEvent({ countries: [], lon: undefined, lat: undefined }));
    const located = confidenceOf(makeEvent());
    expect(noLocation).toBeLessThan(located);
  });
});
