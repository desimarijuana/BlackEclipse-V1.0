// ── Investor Eye — event clustering & confidence ─────────────────────────────
// Turns many raw records (dozens of articles about one real-world event) into
// a small number of clustered events, and scores each cluster's data-quality
// confidence.
//
// Clustering is intentionally simple and explainable (spec §15/§16): time
// proximity + country overlap + event type + title token similarity. No
// embeddings, no LLM — deterministic and unit-testable.
//
// `confidence` is INTERNAL data quality. It is never shown as "certainty".

import type { NormalizedEvent, SourceRef } from './types';
import { severityWeight } from './classify';

/** How close in time two records must be to join the same cluster. */
export const CLUSTER_WINDOW_HOURS = 6;
/** Jaccard similarity of significant title tokens required to merge. */
const TITLE_SIMILARITY_THRESHOLD = 0.34;

const STOP_WORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'at',
  'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'it', 'its',
  'this', 'that', 'these', 'those', 'after', 'before', 'over', 'under', 'up',
  'down', 'new', 'say', 'says', 'said', 'amid', 'into', 'out', 'will', 'has',
  'have', 'had', 'not', 'but', 'than', 'then', 'their', 'his', 'her', 'they',
]);

export function significantTokens(title: string): Set<string> {
  const tokens = title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 3 && !STOP_WORDS.has(t) && !/^\d+$/.test(t));
  return new Set(tokens);
}

/** Jaccard similarity of two token sets (0..1). */
export function tokenSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  for (const t of a) if (b.has(t)) intersection++;
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

function hoursBetween(aIso: string, bIso: string): number {
  const a = Date.parse(aIso);
  const b = Date.parse(bIso);
  if (Number.isNaN(a) || Number.isNaN(b)) return Number.POSITIVE_INFINITY;
  return Math.abs(a - b) / 36e5;
}

function shareCountry(a: string[], b: string[]): boolean {
  if (a.length === 0 || b.length === 0) return false;
  return a.some((c) => b.includes(c));
}

/**
 * Should `candidate` merge into `existing`? Conservative on purpose: a merge
 * requires the same type AND (shared country OR strong title similarity) AND
 * time proximity. Under-merging is safer than fusing two real events.
 */
export function shouldCluster(existing: NormalizedEvent, candidate: NormalizedEvent): boolean {
  if (existing.eventType !== candidate.eventType) return false;
  if (hoursBetween(existing.publishedAt, candidate.publishedAt) > CLUSTER_WINDOW_HOURS) return false;
  const sameCountry = shareCountry(existing.countries, candidate.countries);
  const sim = tokenSimilarity(significantTokens(existing.title), significantTokens(candidate.title));
  if (sameCountry && sim >= 0.15) return true;
  if (sim >= TITLE_SIMILARITY_THRESHOLD) return true;
  // No location at all on either side, very similar titles.
  if (!sameCountry && sim >= 0.5) return true;
  return false;
}

function mergeSources(a: SourceRef[], b: SourceRef[]): SourceRef[] {
  const seen = new Set<string>();
  const out: SourceRef[] = [];
  for (const s of [...a, ...b]) {
    const key = s.id || s.url || s.name;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

function uniq<T>(arr: T[]): T[] {
  return [...new Set(arr)];
}

/** Merge `candidate` into `target` (mutating a copy), keeping the earliest time. */
export function mergeEvents(target: NormalizedEvent, candidate: NormalizedEvent): NormalizedEvent {
  const sources = mergeSources(target.sources, candidate.sources);
  const earliest =
    Date.parse(target.publishedAt) <= Date.parse(candidate.publishedAt)
      ? target.publishedAt
      : candidate.publishedAt;
  // Prefer the longer title/summary — usually the most informative phrasing.
  const title = candidate.title.length > target.title.length ? candidate.title : target.title;
  const summary =
    (candidate.summary?.length ?? 0) > (target.summary?.length ?? 0)
      ? candidate.summary
      : target.summary;
  const severity =
    severityWeight(candidate.severity) > severityWeight(target.severity)
      ? candidate.severity
      : target.severity;

  return {
    ...target,
    title,
    summary,
    severity,
    countries: uniq([...target.countries, ...candidate.countries]),
    channels: uniq([...target.channels, ...candidate.channels]),
    commodities: uniq([...target.commodities, ...candidate.commodities]),
    sectors: uniq([...target.sectors, ...candidate.sectors]),
    securities: uniq([...target.securities, ...candidate.securities]),
    sources,
    sourceCount: sources.length,
    publishedAt: earliest,
  };
}

/**
 * Cluster a flat list of normalized events. Deterministic: iterates in input
 * order, so the same inputs always yield the same clusters (important for the
 * unique `dedupKey` upserts to be stable).
 */
export function clusterEvents(events: NormalizedEvent[]): NormalizedEvent[] {
  const clusters: NormalizedEvent[] = [];
  for (const event of events) {
    // Find the best (most similar) existing cluster to merge into.
    let bestIndex = -1;
    let bestScore = 0;
    for (let i = 0; i < clusters.length; i++) {
      if (!shouldCluster(clusters[i], event)) continue;
      const score = tokenSimilarity(
        significantTokens(clusters[i].title),
        significantTokens(event.title),
      );
      if (score >= bestScore) {
        bestScore = score;
        bestIndex = i;
      }
    }
    if (bestIndex === -1) {
      clusters.push(event);
    } else {
      clusters[bestIndex] = mergeEvents(clusters[bestIndex], event);
    }
  }
  // Re-score confidence after merging so multi-source clusters rank higher.
  return clusters.map((c) => ({ ...c, confidence: confidenceOf(c) }));
}

// ── Confidence ───────────────────────────────────────────────────────────────

const SOURCE_QUALITY: Record<string, number> = {
  gdelt: 0.7,
  usgs: 0.95,
  news: 0.6,
};

function hasCoords(e: NormalizedEvent): boolean {
  return typeof e.lon === 'number' && typeof e.lat === 'number';
}

/**
 * Internal data-quality confidence, 0..1. Factors (spec §16):
 * independent-source count, source quality, country/location extraction,
 * and type/severity consistency. It is NOT a probability the event is true.
 */
export function confidenceOf(event: NormalizedEvent): number {
  // Independent sources: saturates at 5 confirmations.
  const sourceFactor = Math.min(1, Math.log2(event.sourceCount + 1) / Math.log2(6));
  const primaryQuality = SOURCE_QUALITY[event.primarySource] ?? 0.5;
  const sourceQuality = Math.min(1, primaryQuality + (event.sourceCount - 1) * 0.05);
  const geoFactor = hasCoords(event) ? 1 : event.countries.length > 0 ? 0.75 : 0.35;
  const entityFactor = Math.min(1, event.countries.length / 2 + (hasCoords(event) ? 0.5 : 0));

  const score = sourceFactor * 0.4 + sourceQuality * 0.25 + geoFactor * 0.2 + entityFactor * 0.15;
  return Math.max(0.05, Math.min(1, Number(score.toFixed(2))));
}
