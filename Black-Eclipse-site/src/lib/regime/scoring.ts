// ── Market Regime scoring (pure, dependency-free) ────────────────────────────
// All the arithmetic behind a regime reading lives here so it is deterministic,
// unit-testable, and free of I/O. The API route only gathers inputs; this module
// decides scores, renormalized weights, confidence and the regime label.
//
// HONESTY RULES (see AGENTS.md):
//   · A component with no finite score is UNAVAILABLE, never neutral.
//   · A component older than its maxAgeMs is STALE and excluded from the score.
//   · Missing inputs lower confidence (coverage) rather than being fabricated.
//   · If the core price/breadth input is missing, the whole reading is
//     UNAVAILABLE — never a false neutral.

import type {
  RegimeComponent,
  RegimeComponentId,
  RegimeDriver,
  RegimeId,
  RegimeResult,
  RegimeScope,
} from './types';

/** Base weights. Renormalized over whatever is actually available. */
export const REGIME_WEIGHTS: Record<RegimeComponentId, number> = {
  price_breadth: 0.4,
  volatility: 0.2,
  macro_risk: 0.15,
  news_narrative: 0.2,
  positioning: 0.05,
};

/** The one component whose absence makes the whole reading UNAVAILABLE. */
export const CORE_COMPONENT: RegimeComponentId = 'price_breadth';

export const COMPONENT_LABELS: Record<RegimeComponentId, string> = {
  price_breadth: 'Price & breadth',
  volatility: 'Volatility / options',
  macro_risk: 'Macro / risk',
  news_narrative: 'News / narrative',
  positioning: 'Positioning',
};

export const REGIME_LABELS: Record<RegimeId, string> = {
  risk_on_broadening: 'Risk-on broadening',
  fragile_rally: 'Fragile rally',
  mixed: 'Mixed / uncertain',
  risk_off: 'Risk-off',
  narrative_shock: 'Narrative shock',
  unavailable: 'Unavailable',
};

/** State thresholds for the combined score. */
export const REGIME_BULLISH_THRESHOLD = 0.35;
export const REGIME_BEARISH_THRESHOLD = -0.35;

// ── Small numeric helpers ────────────────────────────────────────────────────

function clamp(x: number): number {
  return x < -1 ? -1 : x > 1 ? 1 : x;
}

function finite(x: unknown): x is number {
  return typeof x === 'number' && Number.isFinite(x);
}

/** Compress an unbounded reading into [-1, +1] via tanh. */
export function tanhScore(value: number, scale = 1.5): number {
  if (!finite(value) || scale <= 0) return 0;
  return clamp(Math.tanh(value / scale));
}

/** Resolve the market a scope should read. `selected` falls back to US. */
export function resolveRegimeMarket(
  scope: RegimeScope,
  selectedMarket: string | null | undefined,
): string {
  if (scope === 'us') return 'US';
  if (scope === 'global') return 'GLOBAL';
  const m = selectedMarket?.trim();
  return m ? m.toUpperCase() : 'US';
}

/** Compact age label for freshness UI ("just now", "12m ago", "3h ago", "2d ago"). */
export function formatAge(ageMs: number | null | undefined): string {
  if (!finite(ageMs) || ageMs < 0) return 'unknown';
  const mins = Math.floor(ageMs / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ── Component scorers ────────────────────────────────────────────────────────

/**
 * Price & breadth: index average return plus breadth nudges.
 * `breadthUp` and `sectorUp` are fractions in [0,1] (null when unknown).
 */
export function scorePriceBreadth(
  avgChangePct: number,
  breadthUp: number | null,
  sectorUp: number | null,
): number {
  if (!finite(avgChangePct)) return 0;
  const b = finite(breadthUp) ? (clamp(breadthUp) - 0.5) * 0.6 : 0;
  const s = finite(sectorUp) ? (clamp(sectorUp) - 0.5) * 0.3 : 0;
  return tanhScore(avgChangePct + b + s, 1.5);
}

/** Volatility: low VIX reads risk-on, high VIX reads risk-off. Null if absent. */
export function scoreVolatility(vix: number | null | undefined): number | null {
  if (!finite(vix) || vix <= 0) return null;
  // 12 → +0.5, 20 → 0, 32 → -0.75 (clamped).
  return clamp((20 - vix) / 16);
}

export interface MacroSurprise {
  actual: number;
  forecast: number;
  importance: 'high' | 'medium' | 'low';
  /** +1 when above-forecast is risk-on; -1 when it is risk-off. */
  polarity: 1 | -1;
}

const IMPORTANCE_WEIGHT: Record<MacroSurprise['importance'], number> = {
  high: 1,
  medium: 0.6,
  low: 0.3,
};

/** Macro surprises: actual vs forecast on recent releases (+ rate changes). */
export function scoreMacroSurprises(surprises: MacroSurprise[]): number | null {
  if (!Array.isArray(surprises) || surprises.length === 0) return null;
  let net = 0;
  let total = 0;
  for (const s of surprises) {
    if (!finite(s.actual) || !finite(s.forecast)) continue;
    const denom = Math.max(Math.abs(s.forecast) * 0.1, 0.05);
    const surprise = Math.max(-1, Math.min(1, (s.actual - s.forecast) / denom));
    const weight = IMPORTANCE_WEIGHT[s.importance] ?? 0.6;
    net += surprise * s.polarity * weight;
    total += weight;
  }
  if (total <= 0) return null;
  return clamp(Math.tanh((net / total) * 1.2));
}

export interface NewsScoredItem {
  sentiment: 'bullish' | 'bearish' | 'neutral';
  tier: number | null;
  /** Epoch ms. */
  at: number;
  /** Market relevance multiplier (0..1]; higher = more on-topic. */
  relevance: number;
}

export const NEWS_TIER_WEIGHTS: Record<number, number> = { 1: 4, 2: 2.5, 3: 1.5, 4: 1 };
export const NEWS_HALF_LIFE_HOURS = 12;

/**
 * Continuous news score: source-tier weighted, recency-decayed, relevance
 * weighted. Neutral items add weight (so a quiet tape reads ~0) but no net
 * direction. Returns null when there is no usable item.
 */
export function scoreNews(
  items: NewsScoredItem[],
  now: number,
  halfLifeHours = NEWS_HALF_LIFE_HOURS,
): number | null {
  if (!Array.isArray(items) || items.length === 0) return null;
  let net = 0;
  let total = 0;
  for (const it of items) {
    if (!finite(it.at)) continue;
    const ageH = Math.max(0, (now - it.at) / 3_600_000);
    const decay = Math.pow(0.5, ageH / halfLifeHours);
    const weight = (NEWS_TIER_WEIGHTS[it.tier ?? 3] ?? 1.5) * decay * Math.max(0, it.relevance);
    const signed = it.sentiment === 'bullish' ? 1 : it.sentiment === 'bearish' ? -1 : 0;
    net += signed * weight;
    total += weight;
  }
  if (total <= 0) return null;
  return clamp(Math.tanh((net / total) * 1.6));
}

/** Which news-feed regions count as "on market" for a JDDS market. */
export function marketNewsRegions(market: string): string[] {
  const m = (market || 'US').toUpperCase();
  switch (m) {
    case 'GLOBAL':
      return ['GLOBAL', 'US', 'EU', 'UK', 'ASIA', 'INDIA', 'MENA'];
    case 'US':
      return ['US', 'GLOBAL'];
    case 'UK':
      return ['UK', 'EU', 'GLOBAL'];
    case 'DE':
    case 'FR':
    case 'NL':
    case 'EU':
      return ['EU', 'UK', 'GLOBAL'];
    case 'IN':
      return ['INDIA', 'ASIA', 'GLOBAL'];
    case 'PK':
    case 'CN':
    case 'TW':
    case 'HK':
    case 'JP':
    case 'KR':
    case 'SG':
    case 'MY':
    case 'AU':
    case 'ID':
    case 'TH':
    case 'VN':
      return ['ASIA', 'INDIA', 'GLOBAL'];
    case 'SA':
    case 'AE':
    case 'EG':
    case 'ZA':
    case 'NG':
    case 'TR':
      return ['MENA', 'GLOBAL'];
    default:
      return ['GLOBAL'];
  }
}

// ── Assembly ─────────────────────────────────────────────────────────────────

export interface RawComponent {
  id: RegimeComponentId;
  score: number | null;
  asOf: number | null;
  maxAgeMs: number;
  source: string;
  detail: string;
  confidence?: number;
  metrics?: Record<string, number>;
}

export interface AssembleInput {
  scope: RegimeScope;
  market: string;
  benchmarkSymbol?: string | null;
  raw: RawComponent[];
  drivers?: RegimeDriver[];
  now?: number;
}

function classify(
  score: number,
  components: RegimeComponent[],
): RegimeId {
  const price = components.find((c) => c.id === 'price_breadth');
  const vol = components.find((c) => c.id === 'volatility');
  const news = components.find((c) => c.id === 'news_narrative');

  const volUsable = vol?.available && finite(vol.score);
  const newsUsable = news?.available && finite(news.score);

  // Narrative shock: a strongly negative news tape that price does not confirm.
  if (newsUsable && (news!.score as number) <= -0.6) {
    const priceWeak = !price?.available || !finite(price.score) || (price.score as number) > -0.2;
    if (priceWeak) return 'narrative_shock';
  }

  if (score <= REGIME_BEARISH_THRESHOLD) return 'risk_off';
  if (volUsable && (vol!.score as number) <= -0.5) return 'risk_off';

  if (score >= REGIME_BULLISH_THRESHOLD) {
    const breadth = price?.metrics?.breadthUp;
    const volComfortable = !volUsable || (vol!.score as number) > -0.35;
    if (finite(breadth) && breadth >= 0.6 && volComfortable) return 'risk_on_broadening';
    return 'fragile_rally';
  }

  return 'mixed';
}

/**
 * Assemble a `RegimeResult` from raw components: renormalize weights over the
 * available set, compute coverage/freshness/confidence, and classify.
 */
export function assembleRegime(input: AssembleInput): RegimeResult {
  const now = input.now ?? Date.now();
  const components: RegimeComponent[] = [];
  let usableWeight = 0;
  let totalWeight = 0;

  for (const r of input.raw) {
    const weight = REGIME_WEIGHTS[r.id] ?? 0;
    totalWeight += weight;

    const hasScore = finite(r.score);
    const age = r.asOf == null ? null : now - r.asOf;
    const stale = hasScore && (r.asOf == null || (age != null && age > r.maxAgeMs));
    const available = hasScore && !stale;
    if (available) usableWeight += weight;

    components.push({
      id: r.id,
      label: COMPONENT_LABELS[r.id] ?? r.id,
      score: hasScore ? clamp(r.score as number) : null,
      weight,
      usedWeight: 0,
      available,
      asOf: r.asOf,
      maxAgeMs: r.maxAgeMs,
      stale,
      source: r.source,
      detail: !hasScore
        ? r.detail
        : stale
          ? `${r.detail} — stale (${formatAge(age)} old), excluded`
          : r.detail,
      confidence: available ? (r.confidence ?? 1) : 0,
      metrics: r.metrics,
    });
  }

  for (const c of components) {
    if (c.available && usableWeight > 0) c.usedWeight = c.weight / usableWeight;
  }

  const coverage = totalWeight > 0 ? usableWeight / totalWeight : 0;
  let freshness = 0;
  if (usableWeight > 0) {
    let acc = 0;
    for (const c of components) {
      if (!c.available || c.asOf == null) continue;
      const f = clamp(1 - (now - c.asOf) / c.maxAgeMs);
      acc += f * c.weight;
    }
    freshness = acc / usableWeight;
  }
  const confidence = Math.round(coverage * Math.max(0, freshness) * 1000) / 1000;

  const core = components.find((c) => c.id === CORE_COMPONENT);
  const coreAvailable = Boolean(core?.available);

  let score: number | null = null;
  if (coreAvailable && usableWeight > 0) {
    let acc = 0;
    for (const c of components) {
      if (c.available && finite(c.score)) acc += (c.score as number) * c.weight;
    }
    score = Math.round((acc / usableWeight) * 1000) / 1000;
  }

  const regime: RegimeId = coreAvailable && score != null ? classify(score, components) : 'unavailable';

  const usableAges = components.filter((c) => c.available && c.asOf != null).map((c) => c.asOf as number);
  const asOf = usableAges.length > 0 ? Math.max(...usableAges) : null;

  return {
    scope: input.scope,
    market: input.market,
    regime,
    label: REGIME_LABELS[regime],
    score: regime === 'unavailable' ? null : score,
    confidence: regime === 'unavailable' ? 0 : confidence,
    coverage: Math.round(coverage * 1000) / 1000,
    components,
    drivers: input.drivers ?? [],
    benchmarkSymbol: input.benchmarkSymbol ?? null,
    asOf,
    builtAt: now,
    source: 'jdds',
    coreAvailable,
  };
}
