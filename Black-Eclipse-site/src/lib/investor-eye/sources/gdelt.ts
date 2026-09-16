// ── Investor Eye — GDELT source ──────────────────────────────────────────────
// PRIMARY PATH: the GDELT 2.0 **bulk Event export** (`data.gdeltproject.org/
// gdeltv2/`). Every 15 minutes GDELT publishes a zipped tab-separated file of
// machine-coded events. Measured from this host: ~120 KB, downloads in under a
// second, is NOT rate-limited, and carries far richer structure than headlines
// (CAMEO codes, actor names, Goldstein scores, exact action coordinates).
//
// WHY NOT THE DOC API (the previous implementation): `api.gdeltproject.org/
// api/v2/doc/doc` was measured at >13s per request AND returning HTTP 429 on
// short bursts — while the shared transport (`connectors/security.safeGet`)
// hard-caps timeouts at 10s. It therefore produced ZERO events, every run. It
// is kept only as a best-effort secondary path so a bulk-outage still yields
// something; it is never required.
//
// The zip is decompressed with Node's built-in `zlib` (no new dependency):
// GDELT's zips use a data descriptor, so the compressed size is read from the
// ZIP central directory rather than the local header.

import { safeGet, OutboundError } from '@/lib/connectors/security';
import { classifyChannels, classifyCommodities, classifySectors, classifySeverity, classifyType } from '../classify';
import { classifyCameo, severityFromGoldstein, dyadCountries, quadClassOf } from '../cameo';
import { scoreRelevance, selectRelevant, KEEP_THRESHOLD } from '../relevance';

/**
 * Hard cap on events accepted from one GDELT file. A 15-minute file carries
 * ~1,800 rows; even after relevance filtering the tail is rarely useful, and
 * this bounds both the DB write and the map payload.
 */
const GDELT_MAX_EVENTS = 400;
import { resolveCountry } from '../countries';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import type { EventActor, EventSource, NormalizedEvent, RawEvent, SourceQuery, SourceRef } from '../types';

export const GDELT_SOURCE_ID = 'gdelt';
const GDELT_DOC_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc';
// HTTPS: the transport is https-only, and GDELT's data host serves TLS fine.
const GDELT_LASTUPDATE = 'https://data.gdeltproject.org/gdeltv2/lastupdate.txt';

/** Index of each field we read, in the GDELT 2.0 Event export (61 columns). */
const COL = {
  GLOBALEVENTID: 0,
  YEAR: 3,
  Actor1Name: 6,
  Actor1CountryCode: 7,
  Actor1Type1Code: 12,
  Actor2Name: 16,
  Actor2CountryCode: 17,
  Actor2Type1Code: 22,
  IsRootEvent: 25,
  EventCode: 26,
  EventBaseCode: 27,
  EventRootCode: 28,
  QuadClass: 29,
  GoldsteinScale: 30,
  NumMentions: 31,
  NumSources: 32,
  NumArticles: 33,
  AvgTone: 34,
  ActionGeo_FullName: 52,
  ActionGeo_CountryCode: 53,
  ActionGeo_Lat: 56,
  ActionGeo_Long: 57,
  DATEADDED: 59,
  SOURCEURL: 60,
} as const;

// ── Transport: fetch + gunzip the bulk file ──────────────────────────────────

export interface GdeltBulkFile {
  url: string;
  /** Raw GDELT export rows (already unzipped and split). */
  rows: Array<{ fields: string[]; retrievedAt: string }>;
}

/**
 * Read the ZIP central directory to find the true compressed range, then
 * inflate. GDELT's zips set the "data descriptor" flag, so the local header's
 * compressed size is 0 and must come from the central directory.
 */
export function inflateZipEntry(buf: Buffer, inflateRaw: (b: Buffer) => Buffer): Buffer {
  const EOCD_SIG = Buffer.from([0x50, 0x4b, 0x05, 0x06]);
  const eocd = buf.lastIndexOf(EOCD_SIG);
  if (eocd < 0) throw new Error('not a zip (no end-of-central-directory)');
  const cd = buf.readUInt32LE(eocd + 16);
  if (buf.readUInt32LE(cd) !== 0x02014b50) throw new Error('bad central directory');
  const compSize = buf.readUInt32LE(cd + 20);
  const localOff = buf.readUInt32LE(cd + 42);
  const nameLen = buf.readUInt16LE(localOff + 26);
  const extraLen = buf.readUInt16LE(localOff + 28);
  const dataStart = localOff + 30 + nameLen + extraLen;
  return inflateRaw(buf.subarray(dataStart, dataStart + compSize));
}

/**
 * Parse `lastupdate.txt` → the 15-minute export URL.
 *
 * IMPORTANT: GDELT advertises these files with `http://` URLs, but its host
 * serves them over TLS as well. The shared transport is https-only on purpose,
 * so the scheme is UPGRADED here rather than weakening `safeGet` (verified:
 * `https://data.gdeltproject.org/.../*.export.CSV.zip` returns 200 in ~2s).
 */
export function parseLastUpdate(body: string): string | null {
  // Lines: "<size> <md5> <url>" for export / mentions / gkg. Prefer ".export.".
  const lines = body.trim().split('\n');
  const exportLine = lines.find((l) => l.includes('.export.CSV.zip'));
  const chosen = exportLine ?? lines[0];
  const raw = chosen?.trim().split(/\s+/).pop();
  if (!raw || !raw.startsWith('http')) return null;
  return raw.startsWith('http://') ? `https://${raw.slice('http://'.length)}` : raw;
}

/**
 * Build a normalized event from one GDELT export row.
 * Returns null when the row lacks the minimum identity (id + code).
 */
export function normalizeExportRow(fields: string[], retrievedAt: string): NormalizedEvent | null {
  const id = fields[COL.GLOBALEVENTID];
  const eventCode = fields[COL.EventCode];
  if (!id || !eventCode) return null;

  const actor1 = fields[COL.Actor1Name] || '';
  const actor2 = fields[COL.Actor2Name] || '';
  const actionGeo = fields[COL.ActionGeo_FullName] || '';
  const url = fields[COL.SOURCEURL] || '';
  const lat = Number(fields[COL.ActionGeo_Lat]);
  const lon = Number(fields[COL.ActionGeo_Long]);
  const hasCoords = Number.isFinite(lat) && Number.isFinite(lon) && (lat !== 0 || lon !== 0);
  const goldstein = Number(fields[COL.GoldsteinScale]);
  const quad = fields[COL.QuadClass];

  // Text used for channel/commodity/sector enrichment and classification hints.
  const text = [actor1, actor2, actionGeo, url].filter(Boolean).join(' ');

  const eventType = classifyCameo(eventCode, {
    type: undefined,
    keywords: text,
  });
  const isMaterialConflict = quad === '4';
  const severity = severityFromGoldstein(Number.isFinite(goldstein) ? goldstein : undefined, isMaterialConflict);

  const countries = dyadCountries(fields[COL.ActionGeo_CountryCode], fields[COL.Actor1CountryCode], fields[COL.Actor2CountryCode]);
  // A state-to-state dyad (both actors are countries) is the strongest
  // geopolitical signal GDELT encodes.
  const a1 = fields[COL.Actor1CountryCode]?.trim();
  const a2 = fields[COL.Actor2CountryCode]?.trim();
  const isStateDyad = Boolean(a1 && a2 && a1 !== '---' && a2 !== '---' && a1.length === 3 && a2.length === 3);

  const added = fields[COL.DATEADDED];
  const publishedAt = added
    ? (() => {
        const m = added.match(/^(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})?/);
        if (!m) return retrievedAt;
        const iso = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] ?? '00'}Z`;
        const t = Date.parse(iso);
        return Number.isNaN(t) ? retrievedAt : new Date(t).toISOString();
      })()
    : retrievedAt;

  // A human-readable title from the actors + action location (GDELT has no
  // headline). Built only from real fields — never invented.
  const actorLabel = [actor1, actor2].filter(Boolean).join(' / ');
  const title = [actorLabel || 'Event', actionGeo ? `— ${actionGeo}` : ''].filter(Boolean).join(' ').slice(0, 240)
    || `GDELT event ${id}`;

  // The structured "who": each actor with its own country and type code.
  const actorList: EventActor[] = [
    { name: actor1, countryCode: fields[COL.Actor1CountryCode]?.trim() || undefined, typeCode: fields[COL.Actor1Type1Code]?.trim() || undefined },
    { name: actor2, countryCode: fields[COL.Actor2CountryCode]?.trim() || undefined, typeCode: fields[COL.Actor2Type1Code]?.trim() || undefined },
  ].filter((a) => a.name);

  let host: string | undefined;
  if (url) {
    try { host = new URL(url).host.replace(/^www\./, ''); } catch { /* ignore */ }
  }
  const source: SourceRef = { id: host ?? GDELT_SOURCE_ID, name: host ?? 'GDELT', url: url || undefined, publishedAt };

  const mentions = Number(fields[COL.NumMentions]) || 0;
  const sources = Number(fields[COL.NumSources]) || 0;

  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    summary: actionGeo || undefined,
    // The "who" — GDELT names the actors behind every coded action. This is the
    // detail that makes a conflict intelligible, and it was being discarded.
    ...(actorList.length > 0 ? { actors: actorList } : {}),
    // Provider-native codes, shown verbatim for transparency (never interpreted
    // as a forecast).
    providerCodes: {
      ...(fields[COL.EventRootCode] ? { cameoRoot: fields[COL.EventRootCode] } : {}),
      ...(Number.isFinite(goldstein) ? { goldstein } : {}),
    },
    placeName: actionGeo || undefined,
    // GDELT hands us exact action coordinates — the strongest geo provenance.
    ...(hasCoords ? { geoMethod: 'provider' as const } : {}),
    eventType,
    severity,
    channels: classifyChannels(text),
    commodities: classifyCommodities(text),
    sectors: classifySectors(text),
    securities: [],
    countries,
    lon: hasCoords ? lon : undefined,
    lat: hasCoords ? lat : undefined,
    confidence: 0.5,
    // A GDELT event's mention/source counts are real corroboration signals.
    sourceCount: Math.max(1, sources),
    sources: [source],
    primarySource: GDELT_SOURCE_ID,
    // GDELT assigns each event a GLOBALEVENTID. Two distinct ids are two
    // events, so clustering must never fuzzy-merge them — without this, every
    // event from one city shared the synthesized "— City, Region, Country"
    // title tail and fused into nonsense clusters.
    clusterSignature: `${GDELT_SOURCE_ID}:${id}`,
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  // Mention volume raises confidence, bounded — more coverage is corroboration.
  base.confidence = Math.min(1, confidenceOf(base) + Math.min(mentions / 200, 0.15));

  // Investor relevance: the filter that turns GDELT's raw firehose into a feed
  // worth looking at. Computed from GDELT's own structured fields.
  const relevance = scoreRelevance({
    quadClass: quadClassOf(quad),
    goldstein: Number.isFinite(goldstein) ? goldstein : undefined,
    numMentions: mentions,
    numSources: sources,
    actor1Type: fields[COL.Actor1Type1Code] || undefined,
    actor2Type: fields[COL.Actor2Type1Code] || undefined,
    countries,
    isStateDyad,
    eventType,
    hasEconomicSignal:
      base.channels.length > 0 || base.commodities.length > 0 || base.sectors.length > 0,
  });
  base.relevance = relevance.score;
  base.relevanceReasons = relevance.reasons;

  base.dedupKey = dedupKeyFor(base);
  return base;
}

let inflateRawFn: ((b: Buffer) => Buffer) | null = null;
async function getInflateRaw(): Promise<(b: Buffer) => Buffer> {
  if (!inflateRawFn) {
    const { inflateRawSync } = await import('node:zlib');
    inflateRawFn = inflateRawSync;
  }
  return inflateRawFn;
}

/** Download + decompress the current GDELT bulk export. */
async function fetchBulkExport(timeoutMs?: number): Promise<GdeltBulkFile> {
  // Measured: index ~1s, file ~2.4s. `safeGet` clamps to MAX_TIMEOUT_MS (10s),
  // so this is comfortably inside the transport's ceiling.
  const indexRes = await safeGet({ url: GDELT_LASTUPDATE, timeoutMs: timeoutMs ?? 10_000 });
  if (indexRes.status < 200 || indexRes.status >= 300) {
    throw new OutboundError('network', `GDELT lastupdate HTTP ${indexRes.status}`);
  }
  const url = parseLastUpdate(indexRes.text);
  if (!url) throw new OutboundError('network', 'GDELT lastupdate had no export URL');

  // `binary: true` is required: the shared transport decodes bodies as UTF-8 by
  // default, which replaces invalid byte sequences with U+FFFD and would corrupt
  // the zip beyond recovery.
  const fileRes = await safeGet({ url, timeoutMs: timeoutMs ?? 10_000, binary: true });
  if (fileRes.status < 200 || fileRes.status >= 300) {
    throw new OutboundError('network', `GDELT export HTTP ${fileRes.status}`);
  }
  if (!fileRes.buffer) throw new OutboundError('network', 'GDELT export returned no bytes');
  const inflateRaw = await getInflateRaw();
  const csv = inflateZipEntry(fileRes.buffer, inflateRaw).toString('utf8');
  const retrievedAt = new Date().toISOString();
  const rows = csv
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => ({ fields: line.split('\t'), retrievedAt }));
  if (rows.length === 0) throw new OutboundError('network', 'GDELT export contained no rows');
  return { url, rows };
}

/** Secondary path: the DOC API. Best-effort only; slow and throttled. */
async function fetchDocApi(query: SourceQuery): Promise<RawEvent[]> {
  const params = new URLSearchParams({
    query: '(war OR sanctions OR tariffs OR "central bank" OR protest)',
    mode: 'artlist',
    format: 'json',
    maxrecords: String(query.maxRecords ?? 50),
    timespan: `${Math.max(1, Math.round(query.hours))}h`,
  });
  const res = await safeGet({
    url: `${GDELT_DOC_ENDPOINT}?${params.toString()}`,
    timeoutMs: 10_000,
    headers: { 'user-agent': 'BlackEclipse-InvestorEye/0.1' },
  });
  if (res.status === 429) throw new OutboundError('network', 'GDELT DOC API rate limited (429)');
  if (res.status < 200 || res.status >= 300) throw new OutboundError('network', `GDELT DOC HTTP ${res.status}`);
  const parsed = JSON.parse(res.text) as { articles?: Array<{ url?: string; title?: string; seendate?: string; domain?: string }> };
  const retrievedAt = new Date().toISOString();
  return (parsed.articles ?? []).map((article) => ({
    sourceId: GDELT_SOURCE_ID,
    sourceName: 'GDELT (DOC API)',
    raw: { kind: 'article' as const, article },
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
    // Primary: the bulk export (fast, complete, not rate-limited).
    try {
      const bulk = await fetchBulkExport(query.timeoutMs);
      return bulk.rows.map(({ fields, retrievedAt }) => ({
        sourceId: GDELT_SOURCE_ID,
        sourceName: 'GDELT',
        raw: { kind: 'export' as const, fields },
        retrievedAt,
      }));
    } catch (err) {
      console.warn('[investor-eye:gdelt] bulk export failed:', err instanceof Error ? err.message : err);
    }
    // Secondary: the DOC API. Kept so a bulk outage degrades instead of failing.
    try {
      return await fetchDocApi(query);
    } catch (err) {
      throw new OutboundError(
        'network',
        `GDELT unavailable (bulk export and DOC API both failed): ${err instanceof Error ? err.message : err}`,
      );
    }
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    const events: NormalizedEvent[] = [];
    for (const record of records) {
      const raw = record.raw as
        | { kind: 'export'; fields: string[] }
        | { kind: 'article'; article: { url?: string; title?: string; seendate?: string } };
      if (raw.kind === 'export') {
        const event = normalizeExportRow(raw.fields, record.retrievedAt);
        if (event) events.push(event);
        continue;
      }
      // DOC-API fallback: classify from the headline alone (no CAMEO data).
      const title = (raw.article.title ?? '').trim();
      if (!title) continue;
      const event = normalizeDocArticle(raw.article, title, record.retrievedAt);
      if (event) events.push(event);
    }
    // GDELT codes every machine-readable event including local crime and sport.
    // Keep only the investor-relevant slice, ranked, so neither the map nor the
    // database is flooded with noise.
    const scored = events
      .filter((e) => e.relevance !== undefined && e.relevance >= KEEP_THRESHOLD)
      .map((e) => ({ ...e, relevance: e.relevance as number }));
    return selectRelevant(scored, GDELT_MAX_EVENTS);
  },
};

/** Fallback normalization for a DOC-API article (headline-only). */
function normalizeDocArticle(
  article: { url?: string; title?: string; seendate?: string },
  title: string,
  retrievedAt: string,
): NormalizedEvent | null {
  const m = article.seendate?.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  const publishedAt = m
    ? new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`).toISOString()
    : retrievedAt;
  const text = title;
  // No CAMEO data on this path, so fall back to keyword classification.
  const eventType = classifyType(text);
  const countries: string[] = [];
  let host: string | undefined;
  if (article.url) {
    try { host = new URL(article.url).host.replace(/^www\./, ''); } catch { /* ignore */ }
  }
  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    eventType,
    severity: classifySeverity(text, eventType),
    channels: classifyChannels(text),
    commodities: classifyCommodities(text),
    sectors: classifySectors(text),
    securities: [],
    countries,
    confidence: 0.5,
    sourceCount: 1,
    sources: [{ id: host ?? GDELT_SOURCE_ID, name: host ?? 'GDELT', url: article.url, publishedAt }],
    primarySource: GDELT_SOURCE_ID,
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  const c = resolveCountry(text);
  if (c) base.countries = [c.iso2];
  base.dedupKey = dedupKeyFor(base);
  base.confidence = confidenceOf(base);
  return base;
}


