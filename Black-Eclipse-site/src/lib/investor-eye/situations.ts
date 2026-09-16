// ── Investor Eye — situation timeline ────────────────────────────────────────
// Answers "is this a one-off, or the Nth incident in an escalating run?"
//
// A single event in isolation is not intelligence. "Explosion near Hormuz" means
// something quite different when it is the FOURTH incident in that area this
// week. This groups the window's events into SITUATIONS — by event type and a
// coarse place/country bucket — and reports the recurrence, the span, and the
// severity trend from real timestamps.
//
// Pure: the caller supplies the event list, so it is unit-testable and reusable
// by the dossier and any future alerting.
//
// Honesty rules:
//   - only counts events actually present in the supplied window;
//   - never implies causation between events, only co-location in time/space;
//   - a single-event situation reports count 1 (not "escalating").

import type { EventSeverity, NormalizedEvent, Provenance } from './types';
import { severityWeight } from './classify';
import { countryByIso2 } from './countries';

export interface SituationOccurrence {
  eventId: string;
  title: string;
  severity: EventSeverity;
  publishedAt: string;
  /** Country codes on this occurrence, for the detail line. */
  countries: string[];
}

export interface Situation {
  /** Stable key: `${eventType}|${country}`. */
  key: string;
  eventType: string;
  /** ISO2 of the bucket — recurrence is counted per COUNTRY. */
  country: string;
  /**
   * Human label for the area. The country name, because that is what the count
   * actually covers; labelling a country-wide count with one city would imply
   * the incidents were all there.
   */
  area: string;
  /**
   * The place name the sources most often named, when they agree on one. Shown
   * as extra context, never as the bucket.
   */
  topPlace?: string;
  /** How many distinct places appear (1 = genuinely concentrated). */
  distinctPlaces: number;
  occurrences: SituationOccurrence[];
  count: number;
  /** ISO span across the occurrences (first → last). */
  firstAt: string;
  lastAt: string;
  /** Hours between first and last. */
  spanHours: number;
  /** Highest severity observed. */
  maxSeverity: EventSeverity;
  /**
   * Mean severity weight across occurrences. Rising across the window is the
   * closest thing to an "escalating" signal it is honest to compute.
   */
  meanSeverityWeight: number;
  /** Severity weights in chronological order — the trend, not a prediction. */
  severityTrend: number[];
  /** True when at least 2 occurrences AND the trend ends higher than it started. */
  escalating: boolean;
}

/** Rank for comparing severities. */
const RANK: Record<EventSeverity, number> = { low: 0, medium: 1, high: 2, critical: 3 };

/**
 * The area bucket for an event.
 *
 * Buckets by COUNTRY, not by raw place string. Measured against live data, using
 * the place name fragmented one situation into four ("US", "United States",
 * "Washington", "Washington, District of Columbia, United States") because
 * providers disagree on granularity — the same conflict appeared as four separate
 * "situations". Country is the stable, comparable unit; the most common place
 * name is still shown as the label.
 *
 * Events with no country cannot be bucketed honestly, so they are skipped.
 */
function areaOf(event: NormalizedEvent): { country: string; key: string } | null {
  if (event.countries.length === 0) return null;
  // The first country is the primary anchor (see `dyadCountries` ordering).
  const country = event.countries[0];
  return { country, key: country.toLowerCase() };
}

/**
 * Group events into situations and sort by how much attention they warrant:
 * recurrence first, then severity, then recency.
 *
 * @param minCount Only return situations with at least this many occurrences
 *                 (2 by default — a single event has no recurrence to report).
 */
export function buildSituations(events: NormalizedEvent[], minCount = 2): Situation[] {
  const groups = new Map<string, { eventType: string; country: string; items: NormalizedEvent[] }>();

  for (const e of events) {
    const area = areaOf(e);
    if (!area) continue;
    const key = `${e.eventType}|${area.key}`;
    const g = groups.get(key);
    if (g) g.items.push(e);
    else groups.set(key, { eventType: e.eventType, country: area.country, items: [e] });
  }

  const situations: Situation[] = [];
  for (const [key, g] of groups) {
    if (g.items.length < minCount) continue;

    const items = [...g.items].sort(
      (a, b) => Date.parse(a.publishedAt) - Date.parse(b.publishedAt),
    );
    const topPlace = mostCommonPlace(items);
    const severityTrend = items.map((e) => severityWeight(e.severity));
    const firstAt = items[0].publishedAt;
    const lastAt = items[items.length - 1].publishedAt;
    const spanHours = Math.max(
      0,
      Math.round(((Date.parse(lastAt) - Date.parse(firstAt)) / 36e5) * 10) / 10,
    );
    let maxSeverity: EventSeverity = 'low';
    for (const e of items) if (RANK[e.severity] > RANK[maxSeverity]) maxSeverity = e.severity;
    const meanSeverityWeight =
      Math.round((severityTrend.reduce((a, b) => a + b, 0) / severityTrend.length) * 100) / 100;

    // "Escalating" is deliberately strict: at least 3 points, and the trend must
    // end above where it started by a real margin. Two points is a comparison,
    // not a trend.
    const escalating =
      items.length >= 3 &&
      severityTrend[severityTrend.length - 1] > severityTrend[0] + 0.2;

    situations.push({
      key,
      eventType: g.eventType,
      country: g.country,
      // The count is country-wide, so the label is the country. A place name is
      // surfaced separately as context and is never allowed to imply that a
      // country-wide count happened in one city.
      area: countryName(g.country),
      ...(topPlace ? { topPlace } : {}),
      distinctPlaces: distinctPlaceCount(items),
      occurrences: items.map((e) => ({
        eventId: e.id ?? e.dedupKey,
        title: e.headline ?? e.title,
        severity: e.severity,
        publishedAt: e.publishedAt,
        countries: e.countries,
      })),
      count: items.length,
      firstAt,
      lastAt,
      spanHours,
      maxSeverity,
      meanSeverityWeight,
      severityTrend,
      escalating,
    });
  }

  return situations.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    if (RANK[b.maxSeverity] !== RANK[a.maxSeverity]) return RANK[b.maxSeverity] - RANK[a.maxSeverity];
    return Date.parse(b.lastAt) - Date.parse(a.lastAt);
  });
}

/** Country name for an ISO2, falling back to the raw code. */
function countryName(iso2: string): string {
  return countryByIso2(iso2)?.name ?? iso2;
}

/** How many distinct place names appear across the occurrences. */
function distinctPlaceCount(items: NormalizedEvent[]): number {
  const set = new Set<string>();
  for (const e of items) if (e.placeName) set.add(e.placeName);
  return set.size;
}

/** The place name most occurrences agree on (ties resolved by longest). */
function mostCommonPlace(items: NormalizedEvent[]): string | undefined {
  const counts = new Map<string, number>();
  for (const e of items) {
    if (!e.placeName) continue;
    counts.set(e.placeName, (counts.get(e.placeName) ?? 0) + 1);
  }
  if (counts.size === 0) return undefined;
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || b[0].length - a[0].length)[0][0];
}

/**
 * The situation a given event belongs to, so the dossier can show "4th incident
 * in this area this week" without the caller re-deriving the grouping key.
 */
export function situationForEvent(
  event: NormalizedEvent,
  all: NormalizedEvent[],
): Situation | undefined {
  const area = areaOf(event);
  if (!area) return undefined;
  const key = `${event.eventType}|${area.key}`;
  return buildSituations(all, 1).find((s) => s.key === key);
}

/** Provenance for the grouping, given the window it was computed from. */
export function situationsProvenance(events: NormalizedEvent[]): Provenance {
  return events.length > 0 ? 'LIVE' : 'UNAVAILABLE';
}
