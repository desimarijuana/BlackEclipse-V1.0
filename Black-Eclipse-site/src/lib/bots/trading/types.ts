// ── Trading bot vocabulary ──────────────────────────────────────────────────
// One place for the trading-bot contract shared by the Bots UI, the draft
// builder and the (mirrored) server validation. Pure types + constants only —
// no React, no fetch, no runtime imports, so every module here is unit-testable.

/** How a bot reaches the market. `shadow` never touches a broker. */
export type TradingMode = "shadow" | "demo" | "live";

/** The autonomy ladder. `l0` proposes, `l1` fills demo, `l2` fills live. */
export type TradingTier = "l0" | "l1" | "l2";

/** The band a bot may size inside. It may never exceed the band. */
export type RiskAppetite = "conservative" | "normal" | "aggressive";

/** How order size is decided. */
export type SizingMode = "risk_based" | "user_fixed";

/** A point-in-time trading decision. Persisted on the automation execution. */
export type TradingSignal =
  | "long_entry"
  | "short_entry"
  | "long_exit"
  | "short_exit"
  | "none";

export type TradingAction = "buy" | "sell" | "close" | "none";

export type DecisionOutcome =
  | "filled"
  | "placed"
  | "preview"
  | "refused"
  | "skipped"
  | "failed"
  | "none";

/** A user-visible session window in one IANA zone. */
export interface SessionWindow {
  timezone: string;
  /** 0 = Sunday … 6 = Saturday (the repo's cron vocabulary). */
  weekdays: number[];
  /** "HH:MM" in `timezone`. */
  start: string;
  end: string;
}

/** Trading configuration carried on `action.config` for a `run_strategy` bot. */
export interface TradingConfig {
  strategyId: string;
  strategyVersion: string;
  mode: TradingMode;
  /** Required for demo/live; empty for shadow. */
  connectionId: string;
  /** Symbols the bot may trade. A strategy may name more; this is the subset. */
  symbols: string[];
  /** Symbols the operator removed from the strategy's universe. */
  excludedSymbols: string[];
  /** Discover more symbols from the screener instead of a fixed list. */
  dynamicSymbols: boolean;
  /** Max symbols the bot may hold/scan at once. */
  maxSymbols: number;
  timeframe: string;
  volume: number;
  stopLossPoints: number;
  takeProfitPoints: number;
  maxOrdersPerDay: number;
  session: SessionWindow | null;
  /** The trial prepared by the server (demo/live only). */
  trialId: string;
  /** Preview only: compute the decision, send nothing. */
  dryRun: boolean;
  /** The operator typed the consent phrase once; this is the standing grant. */
  consent: TradingConsent | null;
  /** Visual teaching material attached to the bot. */
  visuals: StrategyVisual[];
  /** Failure-driven improvement loop. */
  learning: LearningPolicy;
}

/** The leash enforced by `trade/authority.py`. */
export interface TradingAuthority {
  tier: TradingTier;
  appetite: RiskAppetite;
  sizingMode: SizingMode;
  requireStop: boolean;
  maxOpenPositions: number;
  maxMarginPerOrder: number;
  cooldownS: number;
  /** Stop the bot for the day when realized losses reach this percent. */
  maxDailyLossPct: number;
  /** Standing consent: never ask for the phrase again for a covered action. */
  autoMode: boolean;
  /** Auto-renew the mandate when it is near expiry or exhausted. */
  autoRenew: boolean;
  /** Turn failure learning on for this bot. */
  learningEnabled: boolean;
  /** Propose an improvement after this many failures with the same code. */
  improveAfterFailures: number;
}

// ── Consent (the "auto mode") ───────────────────────────────────────────────

export interface TradingConsent {
  version: 1;
  /** Always `standing`: the operator authorized this bot in advance. */
  kind: "standing";
  /** Modes this consent covers (never inferred — stored explicitly). */
  modes: TradingMode[];
  grantedAt: string;
  grantedBy: string;
  /** Null means until revoked; a live consent always carries an expiry. */
  expiresAt: string | null;
  revokedAt: string | null;
  autoRenew: boolean;
  /** The limits the operator agreed to. A bot may tighten, never widen. */
  limits: ConsentLimits;
  /** The phrase the operator typed when granting (proof, never re-used). */
  phrase: string;
}

export interface ConsentLimits {
  symbols: string[];
  maxOrdersPerDay: number;
  maxMarginPerOrder: number;
  maxOpenPositions: number;
}

// ── Visual teaching ─────────────────────────────────────────────────────────

export interface StrategyVisual {
  id: string;
  /** `data:image/...;base64,…` — bounded, never a remote URL. */
  dataUrl: string;
  /** What the picture teaches ("entry after the retest"). */
  caption: string;
  mime: string;
  bytes: number;
  addedAt: string;
}

// ── Decisions ───────────────────────────────────────────────────────────────

export interface DecisionRecord {
  botId: string;
  botVersion: number;
  strategyId: string;
  strategyVersion: string;
  mode: TradingMode;
  tier: TradingTier;
  barTs: string | null;
  symbol: string;
  signal: TradingSignal;
  action: TradingAction;
  reason: string;
  indicators: Record<string, number | string | null>;
  risk: {
    allowed: boolean;
    quantity: number | null;
    reasons: string[];
  } | null;
  outcome: DecisionOutcome;
  /** Typed code for a refusal/skip (see `REFUSAL_CODES`). */
  code: string | null;
  orderId: string | null;
  orderStatus: string | null;
  warnings: string[];
}

// ── Learning ────────────────────────────────────────────────────────────────

export interface LearningPolicy {
  enabled: boolean;
  /** Consecutive (or windowed) failures before the bot raises a lesson. */
  threshold: number;
  /** Only offer improvements that make the bot stricter. */
  tightenOnly: boolean;
  /** Ask the operator before applying; auto-apply is opt-in per lesson. */
  requireConsent: boolean;
  /** Last lesson the operator accepted, for audit + de-duplication. */
  lastAcceptedAt: string | null;
  /** When a lesson was last raised, for quiet periods. */
  lastProposedAt: string | null;
  /** Signatures already proposed, so the bot does not nag. */
  proposed: string[];
}

export interface FailurePattern {
  code: string;
  count: number;
  firstAt: string;
  lastAt: string;
  /** Up to three human lines from the failing decisions. */
  samples: string[];
}

export type ImprovementKind = "tighten" | "config" | "repair" | "pause";

export interface ImprovementProposal {
  /** Stable signature: `code:kind:changeHash`. */
  id: string;
  code: string;
  kind: ImprovementKind;
  title: string;
  rationale: string;
  /** A chat-ready sentence the bot says to the operator. */
  message: string;
  /** Config patch to apply on consent. */
  changes: Partial<TradingConfig>;
  /** Authority patch (tighten-only unless the operator raises it). */
  authorityChanges: Partial<TradingAuthority>;
  /** Never widen risk without an explicit operator decision. */
  riskDelta: "lower" | "same" | "higher";
  /** Safe to apply without asking (strictly risk-reducing). */
  autoApplicable: boolean;
}

// ── Reference data ──────────────────────────────────────────────────────────

export const TRADING_MODES: readonly TradingMode[] = ["shadow", "demo", "live"];
export const TRADING_TIERS: readonly TradingTier[] = ["l0", "l1", "l2"];
export const RISK_APPETITES: readonly RiskAppetite[] = [
  "conservative",
  "normal",
  "aggressive",
];

/** The per-appetite band, mirrored from `trade/authority.py`. */
export const APPETITE_BANDS: Record<
  RiskAppetite,
  { riskPerTradePct: number; maxPositions: number; maxOrdersPerDay: number }
> = {
  conservative: { riskPerTradePct: 0.25, maxPositions: 1, maxOrdersPerDay: 2 },
  normal: { riskPerTradePct: 0.5, maxPositions: 2, maxOrdersPerDay: 4 },
  aggressive: { riskPerTradePct: 1.0, maxPositions: 3, maxOrdersPerDay: 8 },
};

export const MAX_SYMBOLS = 8;
export const MIN_MAX_ORDERS_PER_DAY = 1;
export const MAX_MAX_ORDERS_PER_DAY = 20;

/** Timeframe → milliseconds, for freshness checks. */
export const TIMEFRAME_MS: Record<string, number> = {
  M1: 60_000,
  M5: 300_000,
  M15: 900_000,
  M30: 1_800_000,
  H1: 3_600_000,
  H4: 14_400_000,
  D1: 86_400_000,
  W1: 604_800_000,
};
