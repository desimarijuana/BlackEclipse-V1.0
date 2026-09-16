// ── Investor Eye — news-corpus enrichment ────────────────────────────────────
// GDELT's bulk export carries NO headline — only the article URL — so a GDELT
// event could not show what the story actually said. The repo already ingests
// ~70 RSS feeds into `NewsItem` with real headlines and summaries.
//
// Measured: matching by raw URL string recovered 0/500 events (feeds add
// query strings, tracking params and trailing slashes). Normalizing to
// host + path recovers a real, if modest, fraction — and it is free: one DB
// read, no network, no new feed, no credentials.
//
// Honest by construction: a miss leaves the fields null. We never synthesize a
// headline from the actors, because a fabricated headline reads as reporting
// that does not exist.

import { prisma } from '@/lib/db';
import type { NormalizedEvent } from './types';

/** Canonical comparison key for an article URL: host (sans www) + path. */
export function articleKey(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    const host = u.host.replace(/^www\./, '').toLowerCase();
    const path = u.pathname.replace(/\/+$/, '').toLowerCase();
    if (!host || !path) return null;
    return `${host}${path}`;
  } catch {
    return null;
  }
}

export interface NewsMatch {
  headline: string;
  summary: string | null;
  source: string;
  url: string | null;
  timestamp: Date;
}

/**
 * Look up real headlines for a batch of events by matching their source URLs
 * against the ingested `NewsItem` corpus.
 *
 * Reads every URL in the batch in one query per chunk, then joins in memory —
 * bounded and cheap. Returns a map of eventId → best match (the earliest
 * article, so the enrichment describes the event's first report).
 */
export async function enrichEventsWithHeadlines(
  events: NormalizedEvent[],
): Promise<Map<string, NewsMatch>> {
  const out = new Map<string, NewsMatch>();
  if (events.length === 0) return out;

  // Build the key → eventId index, keeping the first URL per event (GDELT puts
  // the primary article first).
  const keyToEvent = new Map<string, string>();
  for (const e of events) {
    const id = e.id ?? e.dedupKey;
    for (const src of e.sources) {
      const key = articleKey(src.url);
      if (key && !keyToEvent.has(key)) keyToEvent.set(key, id);
    }
  }
  if (keyToEvent.size === 0) return out;

  try {
    // SQLite cannot index the derived host+path form, so we read a bounded
    // recent slice and match in memory. 6k rows is ~0.7s and covers the whole
    // rolling news window.
    const rows = await prisma.newsItem.findMany({
      where: { url: { not: null } },
      orderBy: { timestamp: 'desc' },
      take: 6000,
      select: { headline: true, summary: true, source: true, url: true, timestamp: true },
    });

    for (const row of rows) {
      const key = articleKey(row.url);
      if (!key || !keyToEvent.has(key)) continue;
      const eventId = keyToEvent.get(key)!;
      // Earliest wins: describes the event's first report.
      const prev = out.get(eventId);
      if (!prev || row.timestamp < prev.timestamp) {
        out.set(eventId, {
          headline: row.headline,
          summary: row.summary,
          source: row.source,
          url: row.url,
          timestamp: row.timestamp,
        });
      }
    }
  } catch (err) {
    // Enrichment is best-effort: a failure must never break ingestion.
    console.warn('[investor-eye] headline enrichment skipped:', err instanceof Error ? err.message : err);
  }
  return out;
}

/**
 * Apply enrichment to events in place (returning the updated list). Only fills
 * fields that are actually missing — a source-provided headline always wins.
 */
export function applyHeadlineEnrichment(
  events: NormalizedEvent[],
  matches: Map<string, NewsMatch>,
): NormalizedEvent[] {
  if (matches.size === 0) return events;
  return events.map((e) => {
    const id = e.id ?? e.dedupKey;
    const m = matches.get(id);
    if (!m) return e;
    return {
      ...e,
      headline: e.headline ?? m.headline,
      description: e.description ?? m.summary ?? undefined,
    };
  });
}
