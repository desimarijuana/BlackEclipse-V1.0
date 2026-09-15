// ── Result ranking ──────────────────────────────────────────────────────────
// Weighted, additive scoring. Exact matches beat prefix; prefix beats fuzzy;
// aliases beat keywords. Kind boosts and recency/popularity act as multipliers.

import type { SearchEntity } from './types';

/** Normalize text for matching (lowercase, trim, collapse spaces). */
export function norm(s: string): string {
  return s.toLowerCase().replace(/\s+/g, ' ').trim();
}

export interface RankInput {
  entity: SearchEntity;
  query: string; // normalized query
  currentTab?: string;
  recencyScore?: number; // 0..1
}

const KIND_BOOST: Record<string, number> = {
  indicator: 1.15,
  action: 1.1,
  security: 1.05,
  page: 1.0,
  instrument: 1.05,
  report: 0.9,
  user: 1.0,
  doc: 0.9,
  agent: 1.0,
  event: 1.0,
};

/**
 * Score a single entity against the query. Returns the match tier so callers
 * can, e.g., skip fuzzy results entirely when exact matches exist.
 */
export function scoreEntity({ entity, query, currentTab, recencyScore = 0 }: RankInput): number {
  const q = norm(query);
  if (!q) return 0;

  const symbol = entity.symbol ? norm(entity.symbol) : '';
  const title = norm(entity.title);
  const aliases = entity.keywords.map(norm); // treat keywords as aliases here

  // Tier 1 — exact symbol.
  if (symbol && symbol === q) return base(1000, entity, currentTab, recencyScore);
  // Tier 2 — exact title.
  if (title === q) return base(950, entity, currentTab, recencyScore);
  // Tier 3 — exact keyword/alias.
  if (aliases.some((a) => a === q)) return base(900, entity, currentTab, recencyScore);
  // Tier 4 — prefix on symbol.
  if (symbol && symbol.startsWith(q) && q.length >= 2) return base(720, entity, currentTab, recencyScore);
  // Tier 5 — prefix on title.
  if (title.startsWith(q) && q.length >= 2) return base(650, entity, currentTab, recencyScore);
  // Tier 6 — prefix on any keyword/alias.
  if (aliases.some((a) => a.startsWith(q) && q.length >= 2)) return base(600, entity, currentTab, recencyScore);
  // Tier 7 — substring on symbol.
  if (symbol && symbol.includes(q) && q.length >= 2) return base(480, entity, currentTab, recencyScore);
  // Tier 8 — substring on title.
  if (title.includes(q) && q.length >= 2) return base(420, entity, currentTab, recencyScore);
  // Tier 9 — substring on any keyword/alias.
  if (aliases.some((a) => a.includes(q) && q.length >= 2)) return base(380, entity, currentTab, recencyScore);

  return 0;
}

function base(match: number, e: SearchEntity, currentTab?: string, recencyScore = 0): number {
  let s = match;
  const kindBoost = KIND_BOOST[e.kind] ?? 1;
  s *= kindBoost;

  if (e.rankBoost) s *= e.rankBoost;

  // Context: matching the current tab.
  if (currentTab && e.destination.tab === currentTab) s *= 1.1;

  // Recency: recently-visited destinations get a small lift (1.0..1.15).
  s *= 1 + recencyScore * 0.15;

  return s;
}

/** Simple Levenshtein distance (bounded) — used by fuzzy fallback. */
export function editDistance(a: string, b: string, cap = 3): number {
  const m = a.length;
  const n = b.length;
  if (Math.abs(m - n) > cap) return cap + 1;
  const dp: number[] = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const temp = dp[j];
      dp[j] = Math.min(dp[j] + 1, dp[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = temp;
    }
  }
  return dp[n];
}

/** Fuzzy match a query against an entity's title/aliases within `maxDist`. */
export function fuzzyScore(entity: SearchEntity, query: string, maxDist = 2): number {
  const q = norm(query);
  if (q.length < 2) return 0;
  const candidates = [entity.title, entity.symbol, ...entity.keywords]
    .filter((c): c is string => Boolean(c))
    .map(norm);
  let best = Infinity;
  for (const c of candidates) {
    const d = editDistance(q, c, maxDist);
    if (d < best) best = d;
  }
  if (best > maxDist) return 0;
  // Higher match → closer; scale into the 250–600 fuzzy band.
  const closeness = 1 - best / (maxDist + 1);
  const score = 250 + closeness * 350;
  return base(score, entity, undefined, 0);
}

/**
 * Best "did you mean" correction for a query that produced no results. Scans a
 * small entity set (the static registry) for the nearest title within a
 * length-aware edit distance. Returns the original title casing, or undefined.
 */
export function suggestCorrection(
  query: string,
  entities: SearchEntity[],
  maxDist = 2,
): string | undefined {
  const q = norm(query);
  if (q.length < 3) return undefined;
  const max = q.length <= 4 ? Math.min(maxDist, 1) : maxDist;

  let best: { title: string; d: number } | null = null;
  for (const e of entities) {
    if (!e.title) continue;
    const title = norm(e.title);
    // Cheap length gate before running the DP.
    if (Math.abs(title.length - q.length) > max) continue;
    const d = editDistance(q, title, max);
    if (d <= max && (!best || d < best.d)) best = { title: e.title, d };
  }
  return best?.title;
}
