// ── Regime → Aurora visuals ──────────────────────────────────────────────────
// Translates a Market Regime reading into the scalar the Aurora shader consumes,
// without leaking finance logic into the visual layer (Aurora still only ever
// receives a normalized `sentiment` value + a scalar `dim`). Keeps Aurora's
// frosted-glass identity: bullish brightens the green, bearish shifts red, and
// an UNAVAILABLE reading is dimmed to a calm, honest low-signal state rather
// than shown as neutral.

import type { RegimeId, RegimeResult } from './types';

export interface RegimeVisuals {
  /** Sentiment passed to Aurora in [-1, +1]. */
  score: number;
  /** Scales amplitude/blend in [0, 1]; lower = calmer, dimmer glow. */
  dim: number;
}

/**
 * Map a regime result to shader scalars. UNAVAILABLE (or a missing score) has
 * no directional signal, so it renders as a subdued, dimmed neutral — never a
 * confident green.
 */
export function regimeToAurora(result: RegimeResult | null): RegimeVisuals {
  if (!result || result.regime === 'unavailable' || result.score === null) {
    return { score: 0, dim: 0.35 };
  }
  // Narrative shock is news-driven rather than price-confirmed; soften the
  // glow so it reads as caution rather than a strong directional call.
  const dim = result.regime === 'narrative_shock' || result.regime === 'mixed' ? 0.7 : 1;
  return { score: result.score, dim };
}

/** Plain-language blurb for the regime label (shown in the panel). */
export const REGIME_BLURBS: Record<RegimeId, string> = {
  risk_on_broadening: 'Broad participation with contained volatility.',
  fragile_rally: 'Indexes up but leadership is narrow — participation is thin.',
  mixed: 'Inputs disagree; no clear directional consensus.',
  risk_off: 'Broad weakness and/or elevated volatility.',
  narrative_shock: 'A strongly negative news tape that prices have not confirmed.',
  unavailable: 'Core inputs are missing or stale — no trustworthy reading.',
};
