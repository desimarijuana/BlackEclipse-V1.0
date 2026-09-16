// ── Investor Eye — news-derived event source (Phase 4.2) ─────────────────────
// The repo already ingests ~70 RSS feeds into `NewsItem` (≈1,000 items/day with
// sentiment, ticker and region). Investor Eye previously ignored all of it.
//
// This source turns those EXISTING rows into normalized events — no new feed, no
// new credentials, no extra network calls. It is the cheapest large gain
// available, and it covers market/macro/central-bank news that GDELT's CAMEO
// coding handles poorly (GDELT codes actions between actors, not "the Fed held
// rates").
//
// Honest by construction:
//   - timestamps come from the stored row (never re-invented),
//   - an item whose text yields no event type is dropped, not forced,
//   - relevance is scored the same way as GDELT so the feed stays comparable,
//   - only recent, un-consumed-ish items are read (bounded).

import { prisma } from '@/lib/db';
import { classifyChannels, classifyCommodities, classifySectors, classifySeverity, classifyType } from '../classify';
import { extractCountries, countryByIso2, resolveCountry } from '../countries';
import { resolvePlace } from '../places';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import { scoreRelevance, selectRelevant, KEEP_THRESHOLD } from '../relevance';
import type { EventSource, NormalizedEvent, RawEvent, SourceQuery } from '../types';

export const NEWS_SOURCE_ID = 'news';
const NEWS_MAX_EVENTS = 250;

/** A stored news row, as read (mirrors the NewsItem columns we use). */
export interface NewsRow {
  id: string;
  source: string;
  ticker: string | null;
  headline: string;
  summary: string | null;
  sentiment: string;
  timestamp: Date;
  url: string | null;
  category: string | null;
  region: string | null;
}

/**
 * Categories worth turning into events. The feed carries TECH, HEALTHCARE,
 * CLIMATE, CRYPTO etc. — those are news, not world events, and including them
 * drowns the geopolitical signal.
 */
const RELEVANT_CATEGORIES = new Set([
  'GEOPOLITICS', 'POLITICS', 'WAR', 'DEFENSE', 'MARKETS', 'ECONOMIC',
  'CENTRAL BANKS', 'INFLATION', 'JOBS', 'TRADE', 'ENERGY', 'COMMODITIES',
  'BONDS', 'FOREX', 'REGULATORY', 'WAR',
]);

/** Region label → the gazetteer country it implies (when unambiguous). */
const REGION_TO_ISO2: Record<string, string> = {
  US: 'US', INDIA: 'IN', UK: 'GB', EU: 'DE', ASIA: 'CN', MENA: 'SA',
};

/**
 * Classify one stored news item into an event, or null when it is not an event.
 *
 * A news item is only an event when its text actually indicates one — a generic
 * market recap ("stocks drift lower") is not. This is the key honesty rule:
 * dropping an item is better than inventing an event from it.
 */
export function normalizeNewsRow(row: NewsRow, retrievedAt: string): NormalizedEvent | null {
  const headline = (row.headline ?? '').trim();
  if (!headline) return null;

  const text = `${headline} ${row.summary ?? ''}`.trim();
  const eventType = classifyType(text, row.category ?? undefined);

  // `other` from this path almost always means "not really an event".
  if (eventType === 'other') return null;

  const publishedAt = row.timestamp instanceof Date
    ? row.timestamp.toISOString()
    : new Date(row.timestamp).toISOString();

  // Countries: prefer an explicit mention in the text, then an unambiguous
  // region label. (A ticker→country lookup would need the Asset table; the
  // headline almost always names the country when it matters.)
  const countries = extractCountries(text).map((c) => c.iso2);
  if (countries.length === 0 && row.region && REGION_TO_ISO2[row.region]) {
    countries.push(REGION_TO_ISO2[row.region]);
  }
  const primary = countries.length > 0 ? countryByIso2(countries[0]) : resolveCountry(text);

  // Anchor: prefer a NAMED place (city/port/chokepoint/energy hub) over the
  // country centroid. Plotting every US story at the geographic centre of the
  // USA put pins in Kansas and made the map read as wrong; resolving the place
  // the headline actually names fixes that. The country hint keeps a place name
  // that occurs in several countries on the right one.
  const place = resolvePlace(text, countries);
  const anchor = place ?? primary;

  const channels = classifyChannels(text);
  const commodities = classifyCommodities(text);
  const sectors = classifySectors(text);

  const base: NormalizedEvent = {
    dedupKey: '',
    title: headline.slice(0, 240),
    summary: row.summary ? row.summary.slice(0, 400) : undefined,
    // The stored NewsItem row IS the article, so its headline/summary are real
    // and can be surfaced verbatim — unlike GDELT, which has no headline.
    headline: headline.slice(0, 400),
    description: row.summary ? row.summary.slice(0, 800) : undefined,
    placeName: place?.name,
    // Say honestly how the point was determined.
    geoMethod: place ? 'place' : primary ? 'centroid' : undefined,
    eventType,
    severity: classifySeverity(text, eventType),
    channels,
    commodities,
    sectors,
    // The headline may name a security; surface the stored ticker, which the
    // news ingester already validated against the JDSS universe.
    securities: row.ticker ? [row.ticker] : [],
    countries,
    lon: anchor?.lon,
    lat: anchor?.lat,
    confidence: 0.5,
    sourceCount: 1,
    sources: [{
      id: row.source,
      name: row.source,
      url: row.url ?? undefined,
      publishedAt,
    }],
    primarySource: NEWS_SOURCE_ID,
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };

  base.confidence = confidenceOf(base);

  // Same relevance model as GDELT so the merged feed ranks consistently.
  const relevance = scoreRelevance({
    // A news item has no CAMEO coding; use the stored sentiment as a weak
    // hostility hint (bearish market news is often conflict-driven).
    quadClass: undefined,
    goldstein: row.sentiment === 'bearish' ? -3 : undefined,
    numMentions: 1,
    countries,
    isStateDyad: countries.length >= 2,
    eventType,
    hasEconomicSignal: channels.length > 0 || commodities.length > 0 || sectors.length > 0,
  });
  base.relevance = relevance.score;
  base.relevanceReasons = relevance.reasons;
  base.dedupKey = dedupKeyFor(base);
  return base;
}

/** Read recent stored news as raw records. No network — this is a DB read. */
async function readRecentNews(hours: number): Promise<RawEvent[]> {
  const since = new Date(Date.now() - hours * 36e5);
  const rows = await prisma.newsItem.findMany({
    where: { timestamp: { gte: since } },
    orderBy: { timestamp: 'desc' },
    take: 1500,
    select: {
      id: true, source: true, ticker: true, headline: true, summary: true,
      sentiment: true, timestamp: true, url: true, category: true, region: true,
    },
  });
  const retrievedAt = new Date().toISOString();
  return rows
    .filter((r) => !r.category || RELEVANT_CATEGORIES.has(r.category.toUpperCase()))
    .map((r) => ({
      sourceId: NEWS_SOURCE_ID,
      sourceName: 'Market News',
      raw: { row: r as NewsRow },
      retrievedAt,
    }));
}

export const newsSource: EventSource = {
  id: NEWS_SOURCE_ID,
  name: 'Market News (JDDS)',
  capabilities: ['EVENTS'],
  requiresCredentials: false,
  // Always available: the news ingester runs in the background, so this source
  // has no configuration and no network dependency of its own.
  isConfigured: () => true,

  async fetch(query: SourceQuery): Promise<RawEvent[]> {
    return readRecentNews(query.hours);
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    const events: NormalizedEvent[] = [];
    for (const record of records) {
      const { row } = record.raw as { row: NewsRow };
      const event = normalizeNewsRow(row, record.retrievedAt);
      if (event) events.push(event);
    }
    const scored = events
      .filter((e) => e.relevance !== undefined && e.relevance >= KEEP_THRESHOLD)
      .map((e) => ({ ...e, relevance: e.relevance as number }));
    return selectRelevant(scored, NEWS_MAX_EVENTS);
  },
};
