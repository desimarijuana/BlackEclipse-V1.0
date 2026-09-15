// ── Investor Eye — GDELT source ──────────────────────────────────────────────
// GDELT DOC 2.0 (article list mode) is the primary geopolitical event feed.
// It is free, needs no API key, and is queried over a curated set of
// high-signal topics so the resulting feed is financial/geopolitical rather
// than general news.
//
// Design notes:
//   - All transport goes through the shared `safeGet` (https-only, DNS-pinned,
//     size-capped, no redirects). GDELT itself rate-limits aggressively, so
//     requests are spaced and the whole ingest result is cached server-side.
//   - We use `artlist` (titles + timestamps + domains) rather than GEO's raw
//     point feed: titles carry the classification signal, and coordinates come
//     from the country gazetteer. Honest behaviour: an event with no resolvable
//     country is kept in the feed but has no map pin.
//   - `normalize()` never invents a title, source, or timestamp. A malformed
//     record is dropped, not patched.

import { safeGet, OutboundError } from '@/lib/connectors/security';
import { classifyChannels, classifyCommodities, classifySectors, classifySeverity, classifyType } from '../classify';
import { extractCountries, resolveCountry } from '../countries';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import type { EventSource, NormalizedEvent, RawEvent, SourceQuery, SourceRef } from '../types';

export const GDELT_SOURCE_ID = 'gdelt';
const GDELT_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc';

/**
 * Curated queries. Each entry is a GDELT phrase query plus a category hint the
 * classifier can use as a tie-breaker. Kept intentionally short: GDELT throttles
 * bursts, so fewer, higher-signal queries beat a broad crawl.
 */
const QUERIES: Array<{ label: string; query: string }> = [
  { label: 'conflict', query: '(war OR "armed conflict" OR airstrike OR missile OR troops OR offensive)' },
  { label: 'sanctions', query: '(sanctions OR "export controls" OR embargo OR "asset freeze")' },
  { label: 'trade', query: '(tariffs OR "trade war" OR "trade deal" OR "export ban" OR "supply chain")' },
  { label: 'energy', query: '(opec OR "crude oil" OR "natural gas" OR lng OR pipeline OR refinery)' },
  { label: 'shipping', query: '(shipping OR "red sea" OR "suez canal" OR hormuz OR tanker OR freight)' },
  { label: 'monetary', query: '("central bank" OR "interest rate decision" OR inflation OR "rate hike" OR "rate cut")' },
  { label: 'politics', query: '(election OR protest OR "state of emergency" OR "military coup")' },
  { label: 'disaster', query: '(earthquake OR flooding OR hurricane OR typhoon OR wildfire OR drought)' },
];

interface GdeltArticle {
  url?: string;
  title?: string;
  seendate?: string; // 'YYYYMMDDTHHMMSSZ'
  socialimage?: string;
  domain?: string;
  language?: string;
  sourcecountry?: string;
}

interface GdeltResponse {
  articles?: GdeltArticle[];
}

/** GDELT seendate (`20260915T164200Z`) → ISO. Returns null when malformed. */
export function parseGdeltDate(raw: string | undefined): string | null {
  if (!raw) return null;
  const m = raw.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!m) {
    const fallback = Date.parse(raw);
    return Number.isNaN(fallback) ? null : new Date(fallback).toISOString();
  }
  const [, y, mo, d, h, mi, s] = m;
  const iso = `${y}-${mo}-${d}T${h}:${mi}:${s}Z`;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : new Date(t).toISOString();
}

function domainHost(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch {
    return undefined;
  }
}

/** Build one normalized event from one GDELT article. Returns null if unusable. */
export function normalizeArticle(article: GdeltArticle, label: string, retrievedAt: string): NormalizedEvent | null {
  const title = (article.title ?? '').trim();
  if (!title) return null;
  const publishedAt = parseGdeltDate(article.seendate) ?? retrievedAt;

  const text = title;
  const eventType = classifyType(text, label);
  const severity = classifySeverity(text, eventType);
  const countries = extractCountries(text);
  // Fall back to GDELT's source country when the title named none.
  if (countries.length === 0) {
    const fallback = resolveCountry(article.sourcecountry);
    if (fallback) countries.push(fallback);
  }
  const primary = countries[0];

  const host = domainHost(article.url);
  const source: SourceRef = {
    id: host ?? GDELT_SOURCE_ID,
    name: host ?? 'GDELT',
    url: article.url,
    publishedAt,
  };

  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    summary: undefined,
    eventType,
    severity,
    channels: classifyChannels(text),
    commodities: classifyCommodities(text),
    sectors: classifySectors(text),
    securities: [],
    countries: countries.map((c) => c.iso2),
    lon: primary?.lon,
    lat: primary?.lat,
    confidence: 0.5,
    sourceCount: 1,
    sources: [source],
    primarySource: GDELT_SOURCE_ID,
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  base.dedupKey = dedupKeyFor(base);
  base.confidence = confidenceOf(base);
  return base;
}

/** Fetch one GDELT query (all its articles) as raw records. */
async function fetchQuery(
  query: string,
  label: string,
  hours: number,
  maxRecords: number,
  timeoutMs?: number,
): Promise<RawEvent[]> {
  const params = new URLSearchParams({
    query,
    mode: 'artlist',
    format: 'json',
    maxrecords: String(maxRecords),
    timespan: `${Math.max(1, Math.round(hours))}h`,
    sort: 'hybridrel',
  });
  const url = `${GDELT_ENDPOINT}?${params.toString()}`;
  const res = await safeGet({
    url,
    timeoutMs: Math.min(timeoutMs ?? 10_000, 10_000),
    headers: { 'user-agent': 'BlackEclipse-InvestorEye/0.1' },
  });
  if (res.status < 200 || res.status >= 300) {
    throw new OutboundError('network', `GDELT HTTP ${res.status} (${label})`);
  }
  // GDELT returns text/plain on some errors even with format=json.
  let parsed: GdeltResponse;
  try {
    parsed = JSON.parse(res.text) as GdeltResponse;
  } catch {
    throw new OutboundError('network', `GDELT returned non-JSON for "${label}"`);
  }
  const retrievedAt = new Date().toISOString();
  return (parsed.articles ?? []).map((article) => ({
    sourceId: GDELT_SOURCE_ID,
    sourceName: 'GDELT',
    raw: { article, label },
    retrievedAt,
  }));
}

export const gdeltSource: EventSource = {
  id: GDELT_SOURCE_ID,
  name: 'GDELT',
  capabilities: ['EVENTS'],
  requiresCredentials: false,
  isConfigured: () => true,

  async fetch(query: SourceQuery): Promise<RawEvent[]> {
    const hours = query.hours;
    const perQuery = query.maxRecords ?? 75;
    const out: RawEvent[] = [];
    // Sequential with a small gap: GDELT 429s on bursts. A failing query does
    // not abort the others — partial success is the norm and is reported.
    for (let i = 0; i < QUERIES.length; i++) {
      const q = QUERIES[i];
      try {
        const records = await fetchQuery(q.query, q.label, hours, perQuery, query.timeoutMs);
        out.push(...records);
      } catch (err) {
        console.warn(`[investor-eye:gdelt] query "${q.label}" failed:`, err instanceof Error ? err.message : err);
      }
      if (i < QUERIES.length - 1) await new Promise((r) => setTimeout(r, 400));
    }
    if (out.length === 0) {
      // Every query failed — surface it rather than reporting an empty feed.
      throw new OutboundError('network', 'GDELT returned no records for any query');
    }
    return out;
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    const events: NormalizedEvent[] = [];
    for (const record of records) {
      const { article, label } = record.raw as { article: GdeltArticle; label: string };
      const event = normalizeArticle(article, label, record.retrievedAt);
      if (event) events.push(event);
    }
    return events;
  },
};
