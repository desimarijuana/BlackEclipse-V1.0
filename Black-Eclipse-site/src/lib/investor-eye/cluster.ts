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
import { articleKey } from './enrich';

/** How close in time two records must be to join the same cluster. */
export const CLUSTER_WINDOW_HOURS = 6;
/** Jaccard similarity of significant title tokens required to merge outright. */
const TITLE_SIMILARITY_THRESHOLD = 0.34;
/**
 * Similarity required when records merely share a country. Was effectively
 * `0.15` via an `sameCountry && sim >= 0.15` shortcut, which fused unrelated
 * same-country stories (see `stripLocationSuffix`). Kept just under the
 * outright threshold because a shared country is weak corroboration.
 */
const SAME_COUNTRY_SIMILARITY_THRESHOLD = 0.3;

const STOP_WORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'at',
  'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'it', 'its',
  'this', 'that', 'these', 'those', 'after', 'before', 'over', 'under', 'up',
  'down', 'new', 'say', 'says', 'said', 'amid', 'into', 'out', 'will', 'has',
  'have', 'had', 'not', 'but', 'than', 'then', 'their', 'his', 'her', 'they',
]);

/**
 * Strip a trailing location suffix from a title before tokenizing.
 *
 * GDELT has no headline, so `gdelt.ts` synthesizes
 * `ACTOR1 / ACTOR2 — City, Region, Country` (and `summary` is the same geo
 * string). That tail is IDENTICAL for every event from a city, so leaving it in
 * the token set gave unrelated stories a free similarity score — the direct
 * cause of a "16 nearby events" cluster whose sources were a bicycle retailer,
 * a construction PR and a celebrity lawsuit.
 *
 * The location is still authoritative as *location*; it just must not be used as
 * *textual evidence* that two things are the same event.
 */
export function stripLocationSuffix(title: string): string {
  // Split on the em/en dash or hyphen the title builder uses as a separator.
  const idx = title.search(/\s+[—–]\s+|\s+-\s+/);
  return idx > 0 ? title.slice(0, idx) : title;
}

export function significantTokens(title: string): Set<string> {
  const tokens = stripLocationSuffix(title)
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
 * Should `candidate` merge into `existing`?
 *
 * Three regimes, most-precise first:
 *
 * 1. **Same article URL.** GDELT codes ONE ROW PER ACTOR DYAD, so a single
 *    article routinely becomes 30+ events ("CHINA / AUSTRALIA", "BEIJING / UK",
 *    … all from one story). Measured: 62.7% of events shared an article, one
 *    article produced 37. A URL is definitive identity — two records citing the
 *    same article ARE the same event, whatever the actors or title say.
 *
 * 2. **Different records with a provider signature.** A provider id (GDELT
 *    GLOBALEVENTID, USGS feature id) is the identity: distinct ids are distinct
 *    events, and no title similarity may override that. This is what stopped
 *    unrelated same-city stories fusing.
 *
 * 3. **No identity at all** (ordinary articles). Conservative fuzzy merge.
 */
export function shouldCluster(existing: NormalizedEvent, candidate: NormalizedEvent): boolean {
  if (existing.eventType !== candidate.eventType) return false;
  // A `category` is a provider-stated sub-type. `natural_disaster` covers both
  // earthquakes and fires, and those are different physical events — two known,
  // different categories must never fuse.
  if (existing.category && candidate.category && existing.category !== candidate.category) return false;

  // 1. Same article → same event, regardless of anything else.
  const aUrl = primaryArticleKey(existing);
  const bUrl = primaryArticleKey(candidate);
  if (aUrl && bUrl) {
    if (aUrl === bUrl) return true;
    // Two different articles may still describe one event; fall through to the
    // signature/title rules rather than merging on type+country alone.
    if (existing.clusterSignature || candidate.clusterSignature) {
      return Boolean(
        existing.clusterSignature &&
        candidate.clusterSignature &&
        existing.clusterSignature === candidate.clusterSignature,
      );
    }
    if (hoursBetween(existing.publishedAt, candidate.publishedAt) > CLUSTER_WINDOW_HOURS) return false;
    const urlSim = tokenSimilarity(significantTokens(existing.title), significantTokens(candidate.title));
    return shareCountry(existing.countries, candidate.countries)
      ? urlSim >= SAME_COUNTRY_SIMILARITY_THRESHOLD
      : urlSim >= TITLE_SIMILARITY_THRESHOLD;
  }

  // 2. Provider identity.
  if (existing.clusterSignature || candidate.clusterSignature) {
    return Boolean(
      existing.clusterSignature &&
      candidate.clusterSignature &&
      existing.clusterSignature === candidate.clusterSignature,
    );
  }

  // 3. Fuzzy (articles with no URL).
  if (hoursBetween(existing.publishedAt, candidate.publishedAt) > CLUSTER_WINDOW_HOURS) return false;
  const sim = tokenSimilarity(significantTokens(existing.title), significantTokens(candidate.title));
  if (sim >= TITLE_SIMILARITY_THRESHOLD) return true;
  const sameCountry = shareCountry(existing.countries, candidate.countries);
  return sameCountry && sim >= SAME_COUNTRY_SIMILARITY_THRESHOLD;
}

/** Normalized key of an event's primary article URL, if it has one. */
function primaryArticleKey(e: NormalizedEvent): string | null {
  for (const s of e.sources) {
    const key = articleKey(s.url);
    if (key) return key;
  }
  return null;
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

/** Union two actor lists by name, preserving the first-seen order. */
function mergeActors(
  a: NormalizedEvent['actors'],
  b: NormalizedEvent['actors'],
): NormalizedEvent['actors'] {
  if (!a?.length && !b?.length) return undefined;
  const out: NonNullable<NormalizedEvent['actors']> = [];
  const seen = new Set<string>();
  for (const actor of [...(a ?? []), ...(b ?? [])]) {
    const key = actor.name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(actor);
  }
  return out;
}

// Precision order for a merge: an exact fix beats a capital beats a centroid.
// `provider` and `place` are both exact, so they share the top rank.
const GEO_RANK: Record<NonNullable<NormalizedEvent['geoMethod']>, number> = {
  provider: 3, place: 3, capital: 2, centroid: 1,
};

/** Keep the most precise geo provenance across a merge. */
function strongerGeo(
  a: NormalizedEvent['geoMethod'],
  b: NormalizedEvent['geoMethod'],
): NormalizedEvent['geoMethod'] {
  if (!a) return b;
  if (!b) return a;
  return GEO_RANK[a] >= GEO_RANK[b] ? a : b;
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
    // A real headline is never discarded by a merge; the first one wins for
    // determinism (the cluster's identity is anchored on the earliest record).
    headline: target.headline ?? candidate.headline,
    description: target.description ?? candidate.description,
    actors: mergeActors(target.actors, candidate.actors),
    providerCodes: target.providerCodes ?? candidate.providerCodes,
    placeName: target.placeName ?? candidate.placeName,
    // Prefer the strongest geo provenance present in the cluster.
    geoMethod: strongerGeo(target.geoMethod, candidate.geoMethod),
    // A provider-stated category is never dropped by a merge; both sides agree
    // on it (otherwise `shouldCluster` refused), so either value is correct.
    category: target.category ?? candidate.category,
    severity,
    countries: uniq([...target.countries, ...candidate.countries]),
    channels: uniq([...target.channels, ...candidate.channels]),
    commodities: uniq([...target.commodities, ...candidate.commodities]),
    sectors: uniq([...target.sectors, ...candidate.sectors]),
    securities: uniq([...target.securities, ...candidate.securities]),
    sources,
    sourceCount: sources.length,
    publishedAt: earliest,
    // A merged cluster only keeps a signature if BOTH sides agreed on it (which
    // is the only way they merged); otherwise it is undefined so the cluster
    // behaves as an article cluster from here on.
    clusterSignature:
      target.clusterSignature && target.clusterSignature === candidate.clusterSignature
        ? target.clusterSignature
        : undefined,
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
  firms: 0.9,
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
