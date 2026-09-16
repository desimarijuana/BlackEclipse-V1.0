// ── Investor Eye — event alert rules ─────────────────────────────────────────
// "Tell me when something I care about happens." Rules are pure predicates over
// the normalized event feed, so they are deterministic, testable, and
// explainable: `matchRule()` returns the REASONS a rule fired, never just a
// boolean, so the UI can always show why an alert triggered.
//
// Persistence is `SystemConfig` JSON (the repo's existing convention for
// operator settings), so adding rules needs NO schema change. Evaluation is
// on-demand over the cached world state — deliberately not a push/notification
// platform, which the spec says not to overbuild until asked.

import type { EventSeverity, EventType, NormalizedEvent, Provenance } from './types';

export const ALERT_RULES_KEY = 'investor-eye:alert-rules';

/** Severity ordering for "at least this severe" comparisons. */
const SEVERITY_RANK: Record<EventSeverity, number> = { low: 0, medium: 1, high: 2, critical: 3 };

export const ALERT_SEVERITIES: EventSeverity[] = ['low', 'medium', 'high', 'critical'];

/** Every rule the user can express. All predicates are optional and AND-ed. */
export interface EventAlertRule {
  id: string;
  name: string;
  enabled: boolean;
  createdAt: string;
  /** Empty = any event type. */
  eventTypes: EventType[];
  /** Inclusive floor. 'low' means no severity filter. */
  minSeverity: EventSeverity;
  /** 0..1 inclusive floors. 0 means no filter. */
  minConfidence: number;
  minRelevance: number;
  /** ISO2 codes; empty = any country. */
  countries: string[];
  /** Commodity names (case-insensitive substring); empty = any. */
  commodities: string[];
  /** Free-text terms matched against title + summary; empty = any. */
  keywords: string[];
  /** Optional geographic fence around a point. */
  near?: { lat: number; lon: number; radiusKm: number };
}

export interface RuleMatch {
  ruleId: string;
  eventId: string;
  /** Human-readable reasons, shown verbatim in the UI. */
  reasons: string[];
  /** Distance in km when the rule has a `near` fence. */
  distanceKm?: number;
}

export const MAX_RULES = 50;

/** Great-circle distance in km. Deterministic and dependency-free. */
export function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLon = toRad(bLon - aLon);
  const lat1 = toRad(aLat);
  const lat2 = toRad(bLat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.min(1, Math.sqrt(h))));
}

export function defaultRule(partial: Partial<EventAlertRule> = {}): EventAlertRule {
  return {
    id: partial.id ?? `rule-${Math.random().toString(36).slice(2, 10)}`,
    name: partial.name ?? 'New alert',
    enabled: partial.enabled ?? true,
    createdAt: partial.createdAt ?? new Date().toISOString(),
    eventTypes: partial.eventTypes ?? [],
    minSeverity: partial.minSeverity ?? 'high',
    minConfidence: partial.minConfidence ?? 0,
    minRelevance: partial.minRelevance ?? 0,
    countries: partial.countries ?? [],
    commodities: partial.commodities ?? [],
    keywords: partial.keywords ?? [],
    ...(partial.near ? { near: partial.near } : {}),
  };
}

/**
 * Does `event` satisfy `rule`? Returns the matching reasons, or null.
 *
 * A rule with NO predicates set would match everything, which is almost never
 * intended and would make the panel useless — so an empty rule matches nothing
 * and says so.
 */
export function matchRule(event: NormalizedEvent, rule: EventAlertRule): RuleMatch | null {
  if (!rule.enabled) return null;

  const hasPredicate =
    rule.eventTypes.length > 0 ||
    rule.minSeverity !== 'low' ||
    rule.minConfidence > 0 ||
    rule.minRelevance > 0 ||
    rule.countries.length > 0 ||
    rule.commodities.length > 0 ||
    rule.keywords.length > 0 ||
    Boolean(rule.near);
  if (!hasPredicate) return null;

  const reasons: string[] = [];
  const eid = event.id ?? event.dedupKey;

  if (rule.eventTypes.length > 0) {
    if (!rule.eventTypes.includes(event.eventType)) return null;
    reasons.push(`type ${event.eventType}`);
  }

  if (rule.minSeverity !== 'low') {
    if (SEVERITY_RANK[event.severity] < SEVERITY_RANK[rule.minSeverity]) return null;
    reasons.push(`severity ${event.severity} ≥ ${rule.minSeverity}`);
  }

  if (rule.minConfidence > 0) {
    if (event.confidence < rule.minConfidence) return null;
    reasons.push(`confidence ${event.confidence.toFixed(2)} ≥ ${rule.minConfidence}`);
  }

  if (rule.minRelevance > 0) {
    if ((event.relevance ?? 0) < rule.minRelevance) return null;
    reasons.push(`relevance ${Math.round((event.relevance ?? 0) * 100)}% ≥ ${Math.round(rule.minRelevance * 100)}%`);
  }

  if (rule.countries.length > 0) {
    const hit = event.countries.filter((c) => rule.countries.includes(c));
    if (hit.length === 0) return null;
    reasons.push(`country ${hit.join(', ')}`);
  }

  if (rule.commodities.length > 0) {
    const lowered = event.commodities.map((c) => c.toLowerCase());
    const hit = rule.commodities.filter((want) =>
      lowered.some((have) => have.includes(want.toLowerCase())),
    );
    if (hit.length === 0) return null;
    reasons.push(`commodity ${hit.join(', ')}`);
  }

  if (rule.keywords.length > 0) {
    const hay = `${event.title} ${event.summary ?? ''}`.toLowerCase();
    const hit = rule.keywords.filter((k) => k.trim() && hay.includes(k.trim().toLowerCase()));
    if (hit.length === 0) return null;
    reasons.push(`matched "${hit.join('", "')}"`);
  }

  let dist: number | undefined;
  if (rule.near) {
    if (typeof event.lon !== 'number' || typeof event.lat !== 'number') return null;
    dist = distanceKm(rule.near.lat, rule.near.lon, event.lat, event.lon);
    if (dist > rule.near.radiusKm) return null;
    reasons.push(`${dist} km from focus (≤ ${rule.near.radiusKm} km)`);
  }

  return { ruleId: rule.id, eventId: eid, reasons, ...(dist !== undefined ? { distanceKm: dist } : {}) };
}

export interface AlertEvaluation {
  matches: RuleMatch[];
  /** Rules that produced at least one match. */
  triggeredRuleIds: string[];
  evaluated: number;
  provenance: Provenance;
}

/** Evaluate every rule against the event window. Newest events first. */
export function evaluateRules(events: NormalizedEvent[], rules: EventAlertRule[]): AlertEvaluation {
  const matches: RuleMatch[] = [];
  const triggered = new Set<string>();
  for (const rule of rules) {
    if (!rule.enabled) continue;
    for (const event of events) {
      const m = matchRule(event, rule);
      if (m) {
        matches.push(m);
        triggered.add(rule.id);
      }
    }
  }
  return {
    matches,
    triggeredRuleIds: [...triggered],
    evaluated: events.length,
    provenance: events.length > 0 ? 'LIVE' : 'UNAVAILABLE',
  };
}

/**
 * Validate a user-supplied rule. Returns a normalized rule or an error string —
 * rules are persisted and drive evaluation, so bad input must be rejected at
 * the boundary rather than silently coerced.
 */
export function parseRule(input: unknown): { ok: true; rule: EventAlertRule } | { ok: false; error: string } {
  if (!input || typeof input !== 'object') return { ok: false, error: 'Rule must be an object.' };
  const raw = input as Record<string, unknown>;

  const name = typeof raw.name === 'string' ? raw.name.trim().slice(0, 80) : '';
  if (!name) return { ok: false, error: 'Rule name is required.' };

  const eventTypes = Array.isArray(raw.eventTypes)
    ? (raw.eventTypes.filter((t) => typeof t === 'string') as EventType[])
    : [];
  const minSeverity = ALERT_SEVERITIES.includes(raw.minSeverity as EventSeverity)
    ? (raw.minSeverity as EventSeverity)
    : 'high';

  const asUnit = (v: unknown) =>
    typeof v === 'number' && Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;

  const asStrings = (v: unknown, max = 30) =>
    Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()).map((x) => (x as string).trim()).slice(0, max) : [];

  let near: EventAlertRule['near'];
  const rawNear = raw.near as Record<string, unknown> | undefined;
  if (rawNear && typeof rawNear === 'object') {
    const lat = Number(rawNear.lat);
    const lon = Number(rawNear.lon);
    const radiusKm = Number(rawNear.radiusKm);
    if (
      Number.isFinite(lat) && Number.isFinite(lon) && Number.isFinite(radiusKm) &&
      lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && radiusKm > 0
    ) {
      near = { lat, lon, radiusKm: Math.min(radiusKm, 20000) };
    } else {
      return { ok: false, error: 'Geographic focus needs a valid lat, lon and radius.' };
    }
  }

  const rule = defaultRule({
    id: typeof raw.id === 'string' && raw.id ? raw.id : undefined,
    name,
    enabled: raw.enabled !== false,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : undefined,
    eventTypes,
    minSeverity,
    minConfidence: asUnit(raw.minConfidence),
    minRelevance: asUnit(raw.minRelevance),
    countries: asStrings(raw.countries).map((c) => c.toUpperCase()),
    commodities: asStrings(raw.commodities),
    keywords: asStrings(raw.keywords, 10),
    near,
  });

  return { ok: true, rule };
}

/** Preset templates offered in the UI (spec §28's list, made concrete). */
export const RULE_PRESETS: Array<{ id: string; label: string; rule: Partial<EventAlertRule> }> = [
  {
    id: 'conflict-critical',
    label: 'Critical conflict',
    rule: { name: 'Critical conflict', eventTypes: ['conflict', 'military'], minSeverity: 'critical' },
  },
  {
    id: 'shipping-disruption',
    label: 'Shipping disruption',
    rule: { name: 'Shipping disruption', eventTypes: ['shipping'], minSeverity: 'high', keywords: ['port', 'strait', 'canal', 'tanker'] },
  },
  {
    id: 'energy-infrastructure',
    label: 'Energy infrastructure',
    rule: { name: 'Energy infrastructure', eventTypes: ['energy'], minSeverity: 'high' },
  },
  {
    id: 'large-earthquake',
    label: 'Large earthquake',
    rule: { name: 'Large earthquake', eventTypes: ['natural_disaster'], minSeverity: 'high', keywords: ['earthquake'] },
  },
  {
    id: 'commodity-supply',
    label: 'Commodity supply risk',
    rule: { name: 'Commodity supply risk', minSeverity: 'medium', minRelevance: 0.5, commodities: ['Crude Oil', 'Natural Gas', 'Wheat'] },
  },
];
