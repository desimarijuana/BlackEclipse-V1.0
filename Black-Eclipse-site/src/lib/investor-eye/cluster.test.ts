import { describe, it, expect } from 'vitest';
import { clusterEvents, shouldCluster, mergeEvents, tokenSimilarity, significantTokens, confidenceOf, stripLocationSuffix } from './cluster';
import { dedupKeyFor, timeBucket, collapseDuplicateKeys } from './dedup';
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

  // ── Regression: the "16 nearby events" bug ────────────────────────────────
  // GDELT titles are synthesized as `ACTOR / ACTOR — City, Region, Country`, so
  // every event from one city shared that tail. With the old
  // `sameCountry && sim >= 0.15` shortcut, unrelated stories fused into one
  // cluster (a bicycle-retailer article ended up a "source" of an ICC event).

  it('does NOT fuse two unrelated events that only share a country', () => {
    const a = makeEvent({
      title: 'UNITED STATES / AUTHORITIES — Washington, District of Columbia, United States',
      countries: ['US'],
      eventType: 'conflict',
    });
    const b = makeEvent({
      title: 'INDUSTRY / COMPANIES — Washington, District of Columbia, United States',
      countries: ['US'],
      eventType: 'conflict',
    });
    expect(shouldCluster(a, b)).toBe(false);
  });

  it('ignores the synthesized location tail when scoring similarity', () => {
    // Stripping the tail leaves almost no shared tokens, so similarity is low.
    const a = significantTokens('UNITED STATES / AUTHORITIES — Washington, District of Columbia, United States');
    const b = significantTokens('INDUSTRY / COMPANIES — Washington, District of Columbia, United States');
    expect(tokenSimilarity(a, b)).toBeLessThan(0.34);
  });

  it('never fuzzy-merges records carrying a provider signature', () => {
    const a = makeEvent({
      clusterSignature: 'gdelt:111',
      title: 'A / B — Washington, United States',
      countries: ['US'],
      eventType: 'conflict',
    });
    const b = makeEvent({
      clusterSignature: 'gdelt:222',
      title: 'A / B — Washington, United States',
      countries: ['US'],
      eventType: 'conflict',
    });
    // Identical-looking titles, but two distinct GDELT ids → two events.
    expect(shouldCluster(a, b)).toBe(false);
  });

  it('merges records that share the SAME provider signature', () => {
    const a = makeEvent({ clusterSignature: 'gdelt:999', title: 'X — Anywhere' });
    const b = makeEvent({ clusterSignature: 'gdelt:999', title: 'Completely different words here' });
    expect(shouldCluster(a, b)).toBe(true);
  });

  it('never merges a signatured record with an unsigned one', () => {
    const signed = makeEvent({ clusterSignature: 'gdelt:999', title: 'Same story text' });
    const unsigned = makeEvent({ title: 'Same story text' });
    expect(shouldCluster(signed, unsigned)).toBe(false);
  });

  // ── Article identity: the fan-out bug ─────────────────────────────────────
  // GDELT codes ONE ROW PER ACTOR DYAD, so a single article routinely becomes
  // 30+ events. Measured: 62.7% of events shared an article; one produced 37.
  it('merges events that cite the SAME article, whatever the actors say', () => {
    const url = 'https://example.com/news/one-story/?utm_source=x';
    const a = makeEvent({
      title: 'CHINA / AUSTRALIA — Beijing, China',
      countries: ['CN', 'AU'],
      clusterSignature: 'gdelt:1',
      sources: [{ id: 'example.com', name: 'example.com', url }],
    });
    const b = makeEvent({
      title: 'BEIJING / UNITED KINGDOM — United Kingdom',
      countries: ['CN', 'GB'],
      clusterSignature: 'gdelt:2',
      sources: [{ id: 'example.com', name: 'example.com', url: 'http://www.example.com/news/one-story' }],
    });
    // Different actors, different signatures — but one article, so one event.
    expect(shouldCluster(a, b)).toBe(true);
  });

  it('does NOT merge two different articles that share a country', () => {
    const a = makeEvent({
      title: 'UNITED STATES / AUTHORITIES — Washington, United States',
      countries: ['US'],
      sources: [{ id: 'a.com', name: 'a.com', url: 'https://a.com/story-one' }],
    });
    const b = makeEvent({
      title: 'INDUSTRY / COMPANIES — Washington, United States',
      countries: ['US'],
      sources: [{ id: 'b.com', name: 'b.com', url: 'https://b.com/story-two' }],
    });
    expect(shouldCluster(a, b)).toBe(false);
  });

  it('still merges different articles when the provider signature matches', () => {
    const a = makeEvent({ clusterSignature: 'gdelt:7', sources: [{ id: 'a', name: 'A', url: 'https://a.com/x' }] });
    const b = makeEvent({ clusterSignature: 'gdelt:7', sources: [{ id: 'b', name: 'B', url: 'https://b.com/y' }] });
    expect(shouldCluster(a, b)).toBe(true);
  });

  it('keeps the same article apart across different event types', () => {
    const url = 'https://example.com/news/one-story';
    const a = makeEvent({ eventType: 'sanction', sources: [{ id: 'x', name: 'X', url }] });
    const b = makeEvent({ eventType: 'trade', sources: [{ id: 'x', name: 'X', url }] });
    expect(shouldCluster(a, b)).toBe(false);
  });
});

describe('stripLocationSuffix', () => {
  it('removes the GDELT location tail', () => {
    expect(stripLocationSuffix('ACTOR ONE / ACTOR TWO — Washington, DC, United States'))
      .toBe('ACTOR ONE / ACTOR TWO');
    expect(stripLocationSuffix('Something happened - London, UK')).toBe('Something happened');
  });
  it('leaves a title without a suffix untouched', () => {
    expect(stripLocationSuffix('Fed raises rates')).toBe('Fed raises rates');
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

  // ── Regression: a city's worth of unrelated GDELT events must stay apart ──
  it('keeps many same-city GDELT events as distinct events', () => {
    const city = 'Washington, District of Columbia, United States';
    const events = Array.from({ length: 12 }, (_, i) =>
      makeEvent({
        dedupKey: `g${i}`,
        clusterSignature: `gdelt:${1000 + i}`,
        eventType: 'conflict',
        countries: ['US'],
        title: `ORG ${i} / ORG ${i + 1} — ${city}`,
        sources: [{ id: `s${i}`, name: `S${i}` }],
      }),
    );
    const clustered = clusterEvents(events);
    expect(clustered).toHaveLength(12);
    for (const c of clustered) expect(c.sourceCount).toBe(1);
  });

  it('still collapses the SAME story reported by several outlets', () => {
    const events = [
      makeEvent({ dedupKey: 'a', title: 'Port workers strike over pay' }),
      makeEvent({ dedupKey: 'b', title: 'Port workers strike over pay' }),
      makeEvent({ dedupKey: 'c', title: 'Port workers strike over pay dispute' }),
    ];
    const clustered = clusterEvents(events);
    expect(clustered).toHaveLength(1);
    expect(clustered[0].sourceCount).toBe(3);
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

  // Regression: two DISTINCT GDELT events can share type, country, time bucket
  // and even title (titles are synthesized with a city tail). Without the
  // signature in the key they hashed identically and persisted as duplicate
  // rows — 22 duplicates in a 473-event window.
  it('gives distinct provider-signed events distinct keys', () => {
    const a = makeEvent({ clusterSignature: 'gdelt:111', title: 'A / B — Same City' });
    const b = makeEvent({ clusterSignature: 'gdelt:222', title: 'A / B — Same City' });
    expect(dedupKeyFor(a)).not.toBe(dedupKeyFor(b));
  });

  it('is stable for the same signature regardless of title/time', () => {
    const a = makeEvent({ clusterSignature: 'gdelt:111', title: 'One phrasing' });
    const b = makeEvent({ clusterSignature: 'gdelt:111', title: 'Totally different', publishedAt: '2026-09-16T04:00:00.000Z' });
    expect(dedupKeyFor(a)).toBe(dedupKeyFor(b));
  });

  it('still uses the fuzzy signature when no provider id exists', () => {
    const a = makeEvent();
    expect(dedupKeyFor(a)).toBe(dedupKeyFor(a));
    expect(dedupKeyFor(a)).not.toBe(dedupKeyFor(makeEvent({ countries: ['US'] })));
  });

  // ── Article identity in the key ───────────────────────────────────────────
  it('gives same-article events the same key even with different signatures', () => {
    const url = 'https://example.com/news/story/?ref=rss';
    const a = makeEvent({ clusterSignature: 'gdelt:1', sources: [{ id: 'x', name: 'X', url }] });
    const b = makeEvent({ clusterSignature: 'gdelt:2', sources: [{ id: 'x', name: 'X', url: 'http://www.example.com/news/story' }] });
    expect(dedupKeyFor(a)).toBe(dedupKeyFor(b));
  });

  it('scopes the article key by event type', () => {
    const url = 'https://example.com/news/story';
    expect(dedupKeyFor(makeEvent({ eventType: 'sanction', sources: [{ id: 'x', name: 'X', url }] })))
      .not.toBe(dedupKeyFor(makeEvent({ eventType: 'trade', sources: [{ id: 'x', name: 'X', url }] })));
  });

  it('falls back to the signature when no URL is present', () => {
    const a = makeEvent({ clusterSignature: 'gdelt:5', sources: [] });
    const b = makeEvent({ clusterSignature: 'gdelt:5', sources: [], title: 'different' });
    expect(dedupKeyFor(a)).toBe(dedupKeyFor(b));
  });

  it('timeBucket groups within a window', () => {
    expect(timeBucket('2026-09-15T10:00:00.000Z', 6)).toBe(timeBucket('2026-09-15T11:00:00.000Z', 6));
  });
});

describe('collapseDuplicateKeys', () => {
  it('keeps one record per dedupKey and folds in the other sources', () => {
    const a = makeEvent({ dedupKey: 'same', sources: [{ id: 'a', name: 'A' }], sourceCount: 1 });
    const b = makeEvent({ dedupKey: 'same', sources: [{ id: 'b', name: 'B' }], sourceCount: 1, countries: ['US'] });
    const out = collapseDuplicateKeys([a, b]);
    expect(out).toHaveLength(1);
    expect(out[0].sources.map((s) => s.id).sort()).toEqual(['a', 'b']);
    expect(out[0].sourceCount).toBe(2);
    expect(out[0].countries).toContain('US');
  });

  it('prefers the better-attested record', () => {
    const weak = makeEvent({ dedupKey: 'k', sourceCount: 1, title: 'Weak' });
    const strong = makeEvent({ dedupKey: 'k', sourceCount: 5, title: 'Strong', sources: [{ id: 's', name: 'S' }] });
    expect(collapseDuplicateKeys([weak, strong])[0].title).toBe('Strong');
  });

  it('keeps a headline found on either record', () => {
    const noHeadline = makeEvent({ dedupKey: 'k' });
    const withHeadline = makeEvent({ dedupKey: 'k', headline: 'Real headline' });
    expect(collapseDuplicateKeys([noHeadline, withHeadline])[0].headline).toBe('Real headline');
  });

  it('leaves distinct keys untouched', () => {
    const out = collapseDuplicateKeys([makeEvent({ dedupKey: 'a' }), makeEvent({ dedupKey: 'b' })]);
    expect(out).toHaveLength(2);
  });
});

describe('confidenceOf', () => {  it('is bounded 0..1', () => {
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
