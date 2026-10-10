// ── Investor Eye — event relevance scoring ───────────────────────────────────
// GDELT codes EVERY machine-readable event it finds: local crime, sport,
// university meetings, routine statements. Dumping ~1,800 of those onto the map
// produces noise, not intelligence — the exact "I don't see anything valuable"
// problem.
//
// This module scores how INVESTOR-RELEVANT an event is, from GDELT's own
// structured fields (QuadClass, Goldstein, mention counts, actor types, dyad),
// plus the app's existing keyword classification. Pure and testable.

import type { EventType } from './types';

export interface RelevanceInput {
  /** CAMEO quad class: 1 verbal-coop, 2 material-coop, 3 verbal-conflict, 4 material-conflict. */
  quadClass?: number;
  /** Goldstein scale, -10..+10. */
  goldstein?: number;
  /** How many articles mentioned the event. */
  numMentions?: number;
  numSources?: number;
  /** CAMEO actor type codes, e.g. GOV, MIL, BUS, CVL (civilian), MED. */
  actor1Type?: string;
  actor2Type?: string;
  /** Resolved ISO2 countries of the action + actors. */
  countries: string[];
  /** Whether both actors resolved to countries (a state-to-state dyad). */
  isStateDyad: boolean;
  /** Classified event type from CAMEO + keywords. */
  eventType: EventType;
  /** Commodities/sectors/channels detected in the text. */
  hasEconomicSignal: boolean;
}

export interface RelevanceResult {
  /** 0..1 — higher means more worth an investor's attention. */
  score: number;
  /** Why it scored (shown in the UI, never a bare number). */
  reasons: string[];
  /** Whether it clears the display threshold. */
  keep: boolean;
}

/** Event types that are inherently market-relevant. */
const ECONOMIC_TYPES = new Set<EventType>([
  'sanction', 'tariff', 'trade', 'energy', 'shipping', 'monetary', 'fiscal', 'conflict', 'military',
]);

/** Actor codes that indicate state / institutional action rather than private life. */
const SIGNIFICANT_ACTORS = new Set(['GOV', 'MIL', 'COP', 'JUD', 'LEG', 'BUS', 'CVL', 'MED', 'EDU', 'NGO', 'IGO']);

/** Actor codes that are essentially never investor-relevant on their own. */
const NOISE_ACTORS = new Set(['SPORT', 'ENT', 'REL']);

/**
 * Score investor relevance, 0..1.
 *
 * Weights reflect what actually moves markets: state-to-state dyads, material
 * conflict/coercion, economic types, and how widely the event was reported.
 * A widely-reported local crime story still scores low — reach amplifies a
 * signal, it does not create one.
 */
export function scoreRelevance(input: RelevanceInput): RelevanceResult {
  let score = 0;
  const reasons: string[] = [];

  // 1. Material conflict / coercion is the strongest signal (0.30).
  if (input.quadClass === 4) { score += 0.30; reasons.push('material conflict'); }
  else if (input.quadClass === 3) { score += 0.10; reasons.push('verbal conflict'); }

  // 2. Economic event type (0.22).
  if (ECONOMIC_TYPES.has(input.eventType)) {
    score += 0.22;
    reasons.push(input.eventType.replace(/_/g, ' '));
  }

  // 3. Detected economic channel/commodity/sector (0.15).
  if (input.hasEconomicSignal) { score += 0.15; reasons.push('economic channel'); }

  // 4. State-to-state dyad — diplomacy between countries matters (0.15).
  if (input.isStateDyad) { score += 0.15; reasons.push('state-to-state'); }

  // 5. Institutional actors (0.08).
  const actors = [input.actor1Type, input.actor2Type].filter(Boolean) as string[];
  if (actors.some((a) => SIGNIFICANT_ACTORS.has(a))) { score += 0.08; reasons.push('institutional actor'); }

  // 6. Severity of the Goldstein value (0.10).
  if (typeof input.goldstein === 'number' && Number.isFinite(input.goldstein)) {
    if (input.goldstein <= -7) { score += 0.10; reasons.push('high hostility'); }
    else if (input.goldstein <= -3) { score += 0.05; reasons.push('hostile'); }
  }

  // 7. Reach — how widely reported (up to 0.10). A proxy for significance.
  const mentions = input.numMentions ?? 0;
  if (mentions >= 100) { score += 0.10; reasons.push('widely reported'); }
  else if (mentions >= 25) { score += 0.06; }
  else if (mentions >= 8) { score += 0.03; }

  // ── Penalties ──────────────────────────────────────────────────────────────
  // Pure noise actors with no other signal.
  if (actors.length > 0 && actors.every((a) => NOISE_ACTORS.has(a))) {
    score -= 0.25;
    reasons.push('non-market actor');
  }
  // No resolved geography at all.
  if (input.countries.length === 0) score -= 0.10;
  // A single actor name with no second party and no economic type — usually a
  // local incident ("POLICE / Arizona").
  if (!input.isStateDyad && !ECONOMIC_TYPES.has(input.eventType) && !input.hasEconomicSignal) {
    score -= 0.15;
  }

  // Material conflict / severe hostility is the signal this surface exists to
  // show, so it is FLOORED at the display threshold. Without this, a genuine
  // material-conflict event with no resolved country or a single actor took the
  // penalties below and was silently dropped — the "conflicts sometimes don't
  // appear" bug. A floor cannot manufacture signal: it only prevents a real one
  // from being filtered out.
  const materialConflict =
    input.quadClass === 4 || (typeof input.goldstein === 'number' && input.goldstein <= -5);
  const floored = materialConflict ? Math.max(score, KEEP_THRESHOLD) : score;
  if (materialConflict && score < KEEP_THRESHOLD) reasons.push('material conflict (floored)');

  const clamped = Math.max(0, Math.min(1, Number(floored.toFixed(3))));
  return { score: clamped, reasons, keep: clamped >= KEEP_THRESHOLD };
}

/**
 * Display threshold. Tuned so the feed keeps genuine geopolitical/economic
 * activity while dropping local incident noise — deliberately conservative,
 * because a thin, relevant feed beats a dense, useless one.
 */
export const KEEP_THRESHOLD = 0.3;

/**
 * Rank + cap a scored list, keeping the most relevant events. Bounded so a
 * single 15-minute GDELT file (~2k events) cannot flood the map or the DB.
 */
export function selectRelevant<T extends { relevance: number }>(
  scored: T[],
  max = 400,
): T[] {
  return scored
    .filter((e) => e.relevance >= KEEP_THRESHOLD)
    .sort((a, b) => b.relevance - a.relevance)
    .slice(0, max);
}
