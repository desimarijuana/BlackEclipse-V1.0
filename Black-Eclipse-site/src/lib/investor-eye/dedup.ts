// ── Investor Eye — dedup key ─────────────────────────────────────────────────
// Stable identity for a clustered event. The key must be deterministic across
// ingestion runs so JDDS upserts are idempotent and a repeated run never
// creates a duplicate row for the same real-world event.

import crypto from 'node:crypto';
import type { NormalizedEvent } from './types';

/** Bucket an ISO timestamp into CLUSTER_WINDOW-sized windows (default 6h). */
export function timeBucket(iso: string, windowHours = 6): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return 'unknown';
  const bucketMs = windowHours * 36e5;
  return String(Math.floor(ms / bucketMs));
}

function normalizeTitle(title: string): string {
  return title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .filter((t) => t.length >= 3)
    .slice(0, 8)
    .join(' ');
}

/**
 * Hash an event's identity.
 *
 * When the provider supplies a `clusterSignature` (GDELT's GLOBALEVENTID, a
 * USGS feature id) that IS the identity — use it directly. Anything else would
 * collide: two distinct GDELT events can share a type, country, time bucket and
 * even a title (titles are synthesized and end with the same city tail), yet be
 * separate events. The fuzzy signature is only for records with no provider id
 * (news articles).
 *
 * Merging updates the cluster in place, so the key stays anchored on the
 * first/strongest record.
 */
export function dedupKeyFor(event: Pick<NormalizedEvent, 'eventType' | 'countries' | 'publishedAt' | 'title' | 'clusterSignature'>): string {
  if (event.clusterSignature) {
    return crypto.createHash('sha256').update(`sig|${event.clusterSignature}`).digest('hex').slice(0, 40);
  }
  const countries = [...event.countries].sort().join(',');
  const signature = [event.eventType, countries, timeBucket(event.publishedAt), normalizeTitle(event.title)].join('|');
  return crypto.createHash('sha256').update(signature).digest('hex').slice(0, 40);
}

/**
 * Collapse records that ended up sharing a `dedupKey`.
 *
 * The key is also the DB unique constraint, so two records with the same key
 * would render as duplicate list children AND overwrite each other on upsert.
 * Clustering should prevent it, but this is the last line of defence — it keeps
 * the better-attested record (more sources, then earlier) and folds the other's
 * sources in so no evidence is silently dropped.
 */
export function collapseDuplicateKeys(events: NormalizedEvent[]): NormalizedEvent[] {
  const byKey = new Map<string, NormalizedEvent>();
  for (const e of events) {
    const existing = byKey.get(e.dedupKey);
    if (!existing) {
      byKey.set(e.dedupKey, e);
      continue;
    }
    const [keep, fold] = e.sourceCount > existing.sourceCount ? [e, existing] : [existing, e];
    const seen = new Set(keep.sources.map((s) => s.id || s.url || s.name));
    const merged = [...keep.sources];
    for (const s of fold.sources) {
      const k = s.id || s.url || s.name;
      if (seen.has(k)) continue;
      seen.add(k);
      merged.push(s);
    }
    byKey.set(e.dedupKey, {
      ...keep,
      sources: merged,
      sourceCount: merged.length,
      countries: [...new Set([...keep.countries, ...fold.countries])],
      commodities: [...new Set([...keep.commodities, ...fold.commodities])],
      sectors: [...new Set([...keep.sectors, ...fold.sectors])],
      headline: keep.headline ?? fold.headline,
      description: keep.description ?? fold.description,
    });
  }
  return [...byKey.values()];
}
