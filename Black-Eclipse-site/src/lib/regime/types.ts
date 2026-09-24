// ── Market Regime contracts ──────────────────────────────────────────────────
// The explainable replacement for Aurora's opaque 60/40 market+news blend.
// A regime reading is a weighted set of named components; each one exposes its
// score, the weight ACTUALLY applied, availability, timestamp, source and
// confidence. The top-level result adds the transparent regime label.
//
// These types are the wire contract for `GET /api/regime` and the render model
// for the top-bar Market Regime panel. They are intentionally serializable.

/** Which market the reading is scoped to. */
export type RegimeScope = 'selected' | 'us' | 'global';

/** Transparent regime taxonomy — never just bullish/bearish. */
export type RegimeId =
  | 'risk_on_broadening'
  | 'fragile_rally'
  | 'mixed'
  | 'risk_off'
  | 'narrative_shock'
  | 'unavailable';

export type RegimeComponentId =
  | 'price_breadth'
  | 'volatility'
  | 'macro_risk'
  | 'news_narrative'
  | 'positioning';

export interface RegimeComponent {
  id: RegimeComponentId;
  label: string;
  /** Continuous score in [-1, +1], or null when unavailable/stale. */
  score: number | null;
  /** Base weight before renormalization. */
  weight: number;
  /** Weight actually applied after renormalizing over available components. */
  usedWeight: number;
  /** True only when a fresh, finite score exists. */
  available: boolean;
  /** Epoch ms of the newest supporting input, or null. */
  asOf: number | null;
  /** Max age (ms) before the input is treated as stale and excluded. */
  maxAgeMs: number;
  /** True when data existed but is older than maxAgeMs. */
  stale: boolean;
  /** Where the component's data came from (JDDS table / provider label). */
  source: string;
  /** Human explanation of how it scored, or why it is unavailable. */
  detail: string;
  /** Component-level confidence in [0, 1]. */
  confidence: number;
  /** Optional raw metrics backing the score (e.g. breadth ratio). */
  metrics?: Record<string, number>;
}

export interface RegimeDriver {
  headline: string;
  source: string;
  url?: string | null;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  at: number | null;
}

export interface RegimeResult {
  scope: RegimeScope;
  /** Canonical market id for `selected`/`us`; 'GLOBAL' for global scope. */
  market: string;
  regime: RegimeId;
  label: string;
  /** Combined score in [-1, +1]; null when the core input is missing. */
  score: number | null;
  /** Overall confidence in [0, 1] = coverage × freshness. */
  confidence: number;
  /** Weighted coverage of available inputs in [0, 1]. */
  coverage: number;
  components: RegimeComponent[];
  drivers: RegimeDriver[];
  /** Benchmark symbol an alert can watch for this scope, when known. */
  benchmarkSymbol: string | null;
  /** Epoch ms of the newest usable input, or null. */
  asOf: number | null;
  builtAt: number;
  /** Provenance: always JDDS — the agentic layer never uses a second source. */
  source: 'jdds';
  /** False when the core price/breadth input is unavailable. */
  coreAvailable: boolean;
}
