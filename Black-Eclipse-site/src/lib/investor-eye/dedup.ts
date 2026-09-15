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
 * Hash an event's identity. Type + country set + time bucket + a normalized
 * title signature. Merging updates the cluster in place, so the key stays
 * anchored on the first/strongest record.
 */
export function dedupKeyFor(event: Pick<NormalizedEvent, 'eventType' | 'countries' | 'publishedAt' | 'title'>): string {
  const countries = [...event.countries].sort().join(',');
  const signature = [event.eventType, countries, timeBucket(event.publishedAt), normalizeTitle(event.title)].join('|');
  return crypto.createHash('sha256').update(signature).digest('hex').slice(0, 40);
}
