import { describe, it, expect } from 'vitest';
import { articleKey, applyHeadlineEnrichment, type NewsMatch } from './enrich';
import type { NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'ACTOR / ACTOR — Somewhere',
    eventType: 'conflict',
    severity: 'high',
    channels: [],
    commodities: [],
    sectors: [],
    securities: [],
    countries: ['US'],
    confidence: 0.5,
    sourceCount: 1,
    sources: [{ id: 'x', name: 'X', url: 'https://www.example.com/news/story-1/' }],
    primarySource: 'gdelt',
    publishedAt: '2026-09-16T10:00:00.000Z',
    ...overrides,
  };
}

describe('articleKey', () => {
  it('normalizes host, strips www, query and trailing slash', () => {
    expect(articleKey('https://www.example.com/news/story-1/?utm_source=rss')).toBe('example.com/news/story-1');
    expect(articleKey('http://example.com/news/story-1')).toBe('example.com/news/story-1');
  });

  it('makes the two forms above collide — the whole point', () => {
    // This is why exact URL matching scored 0/500: feeds append tracking params
    // and vary the host prefix.
    expect(articleKey('https://www.example.com/a/b/?x=1')).toBe(articleKey('http://example.com/a/b'));
  });

  it('is case-insensitive on host and path', () => {
    expect(articleKey('https://WWW.Example.COM/News/Story')).toBe('example.com/news/story');
  });

  it('returns null for missing or unparseable input', () => {
    expect(articleKey(null)).toBeNull();
    expect(articleKey(undefined)).toBeNull();
    expect(articleKey('not a url')).toBeNull();
    expect(articleKey('https://example.com')).toBeNull(); // no path
  });
});

describe('applyHeadlineEnrichment', () => {
  const match = (headline: string): NewsMatch => ({
    headline,
    summary: 'A real summary from the feed.',
    source: 'AP',
    url: 'https://www.example.com/news/story-1/',
    timestamp: new Date('2026-09-16T09:00:00.000Z'),
  });

  it('fills headline and description from a matched article', () => {
    const [out] = applyHeadlineEnrichment([event()], new Map([['e1', match('Real headline')]]));
    expect(out.headline).toBe('Real headline');
    expect(out.description).toBe('A real summary from the feed.');
  });

  it('never overwrites a headline the source already provided', () => {
    const withHeadline = event({ headline: 'Source headline' });
    const [out] = applyHeadlineEnrichment([withHeadline], new Map([['e1', match('Corpus headline')]]));
    expect(out.headline).toBe('Source headline');
  });

  it('leaves an unmatched event untouched (no fabrication)', () => {
    const [out] = applyHeadlineEnrichment([event()], new Map());
    expect(out.headline).toBeUndefined();
    expect(out.description).toBeUndefined();
  });

  it('falls back to dedupKey when there is no row id', () => {
    const noId = event({ id: undefined });
    const [out] = applyHeadlineEnrichment([noId], new Map([['e1', match('By dedupKey')]]));
    expect(out.headline).toBe('By dedupKey');
  });
});
