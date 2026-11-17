// ── Trading draft (form ⇄ definition) ───────────────────────────────────────
// The Bots UI edits a flat, string-friendly draft; the automation stores the typed
// `action.config` + `executionAuthority`. This module is the ONE translation, so
// the create dialog, the detail panel and the branch that re-opens a bot for
// editing cannot disagree about what was saved.

import { recommendTier } from "./tier";
import { limitsFromEnvelope } from "./consent";
import {
  MAX_MAX_ORDERS_PER_DAY,
  MIN_MAX_ORDERS_PER_DAY,
} from "./types";
import type {
  LearningPolicy,
  RiskAppetite,
  SizingMode,
  StrategyVisual,
  TradingAuthority,
  TradingConfig,
  TradingConsent,
  TradingMode,
  TradingTier,
} from "./types";
import { parseSymbols } from "./symbols";
import {
  hasBlockingIssues,
  validateTradingSetup,
  type TradingContext,
  type TradingIssue,
} from "./validate";

export interface TradingDraft {
  enabled: boolean;
  mode: TradingMode;
  strategyId: string;
  strategyVersion: string;
  connectionId: string;
  /** Comma/space separated in the form. */
  symbolsText: string;
  excludedText: string;
  dynamicSymbols: boolean;
  maxSymbols: number;
  timeframe: string;
  volume: number;
  stopLossPoints: number;
  takeProfitPoints: number;
  maxOrdersPerDay: number;
  sessionEnabled: boolean;
  sessionTimezone: string;
  sessionStart: string;
  sessionEnd: string;
  sessionWeekdays: number[];
  dryRun: boolean;
  // Authority (the leash)
  tier: TradingTier;
  appetite: RiskAppetite;
  sizingMode: SizingMode;
  requireStop: boolean;
  maxOpenPositions: number;
  maxMarginPerOrder: number;
  cooldownS: number;
  maxDailyLossPct: number;
  autoMode: boolean;
  autoRenew: boolean;
  learningEnabled: boolean;
  improveAfterFailures: number;
  // Consent + material
  consent: TradingConsent | null;
  consentPhrase: string;
  visuals: StrategyVisual[];
  /** Filled by the server after `prepare`. */
  trialId: string;
}

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function emptyTradingDraft(): TradingDraft {
  return {
    enabled: false,
    mode: "shadow",
    strategyId: "",
    strategyVersion: "",
    connectionId: "",
    symbolsText: "",
    excludedText: "",
    dynamicSymbols: false,
    maxSymbols: 4,
    timeframe: "H1",
    volume: 0.01,
    stopLossPoints: 150,
    takeProfitPoints: 300,
    maxOrdersPerDay: 2,
    sessionEnabled: false,
    sessionTimezone: browserTimezone(),
    sessionStart: "08:00",
    sessionEnd: "20:00",
    sessionWeekdays: [1, 2, 3, 4, 5],
    dryRun: true,
    tier: "l0",
    appetite: "conservative",
    sizingMode: "risk_based",
    requireStop: true,
    maxOpenPositions: 1,
    maxMarginPerOrder: 0,
    cooldownS: 900,
    maxDailyLossPct: 3,
    autoMode: true,
    autoRenew: true,
    learningEnabled: true,
    improveAfterFailures: 3,
    consent: null,
    consentPhrase: "",
    visuals: [],
    trialId: "",
  };
}

function clamp(value: number, min: number, max: number, fallback: number): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

export function buildTradingAuthority(draft: TradingDraft): TradingAuthority {
  return {
    tier: draft.tier,
    appetite: draft.appetite,
    sizingMode: draft.sizingMode,
    requireStop: draft.requireStop,
    maxOpenPositions: clamp(draft.maxOpenPositions, 1, 10, 1),
    maxMarginPerOrder: clamp(draft.maxMarginPerOrder, 0, 1_000_000, 0),
    cooldownS: clamp(draft.cooldownS, 0, 86_400, 900),
    maxDailyLossPct: clamp(draft.maxDailyLossPct, 0, 50, 3),
    autoMode: draft.autoMode,
    autoRenew: draft.autoRenew,
    learningEnabled: draft.learningEnabled,
    improveAfterFailures: clamp(draft.improveAfterFailures, 2, 10, 3),
  };
}

export function buildLearningPolicy(draft: TradingDraft): LearningPolicy {
  return {
    enabled: draft.learningEnabled,
    threshold: clamp(draft.improveAfterFailures, 2, 10, 3),
    tightenOnly: true,
    requireConsent: true,
    lastAcceptedAt: null,
    lastProposedAt: null,
    proposed: [],
  };
}

export function buildTradingConfig(
  draft: TradingDraft,
  consent: TradingConfig["consent"] = draft.consent,
): TradingConfig {
  return {
    strategyId: draft.strategyId.trim(),
    strategyVersion: draft.strategyVersion.trim(),
    mode: draft.mode,
    connectionId: draft.connectionId.trim(),
    symbols: parseSymbols(draft.symbolsText),
    excludedSymbols: parseSymbols(draft.excludedText),
    dynamicSymbols: draft.dynamicSymbols,
    maxSymbols: clamp(draft.maxSymbols, 1, 8, 4),
    timeframe: draft.timeframe,
    volume: clamp(draft.volume, 0.01, 1000, 0.01),
    stopLossPoints: clamp(draft.stopLossPoints, 0, 100_000, 0),
    takeProfitPoints: clamp(draft.takeProfitPoints, 0, 100_000, 0),
    maxOrdersPerDay: clamp(
      draft.maxOrdersPerDay,
      MIN_MAX_ORDERS_PER_DAY,
      MAX_MAX_ORDERS_PER_DAY,
      2,
    ),
    session: draft.sessionEnabled
      ? {
          timezone: draft.sessionTimezone || browserTimezone(),
          weekdays: draft.sessionWeekdays.slice().sort(),
          start: draft.sessionStart,
          end: draft.sessionEnd,
        }
      : null,
    trialId: draft.trialId,
    dryRun: draft.dryRun,
    consent,
    visuals: draft.visuals,
    learning: buildLearningPolicy(draft),
  };
}

/** The consent scope a draft asks for (what the operator authorizes once). */
export function consentRequestFor(draft: TradingDraft) {
  return {
    mode: draft.mode,
    symbols: parseSymbols(draft.symbolsText),
    maxOrdersPerDay: clamp(
      draft.maxOrdersPerDay,
      MIN_MAX_ORDERS_PER_DAY,
      MAX_MAX_ORDERS_PER_DAY,
      2,
    ),
    maxMarginPerOrder: clamp(draft.maxMarginPerOrder, 0, 1_000_000, 0),
    maxOpenPositions: clamp(draft.maxOpenPositions, 1, 10, 1),
  };
}

export function consentLimitsFor(draft: TradingDraft) {
  return limitsFromEnvelope({
    symbols: parseSymbols(draft.symbolsText),
    maxOrdersPerDay: draft.maxOrdersPerDay,
    maxMarginPerOrder: draft.maxMarginPerOrder,
    maxOpenPositions: draft.maxOpenPositions,
  });
}

/**
 * The exact phrase the server checks. Typing it once is what makes auto mode
 * possible; it is never stored in the automation action.
 */
export function expectedConsentPhrase(
  draft: TradingDraft,
  connectionLabel: string,
  brain: "strategy" | "agent" = "strategy",
): string {
  if (brain === "agent" && draft.mode !== "shadow") {
    return `MANDATE ${draft.mode.toUpperCase()} ${connectionLabel}`;
  }
  if (draft.mode === "live") {
    return `LIVE TRIAL ${draft.strategyId} ${draft.strategyVersion}`;
  }
  return `MANDATE DEMO ${connectionLabel}`;
}

export function validateTradingDraft(
  draft: TradingDraft,
  context: TradingContext,
  consent: TradingConfig["consent"],
  options: { requireStrategy?: boolean } = {},
): { issues: TradingIssue[]; blocked: boolean; config: TradingConfig; authority: TradingAuthority } {
  const config = buildTradingConfig(draft, consent);
  const authority = buildTradingAuthority(draft);
  const issues = validateTradingSetup(config, authority, context, options);
  return { issues, blocked: hasBlockingIssues(issues), config, authority };
}

/**
 * Read a stored `run_strategy` action back into a draft. Defensive: a definition
 * written by an older/newer client must open with sane defaults, never throw.
 */
export function draftFromTradingAction(
  config: unknown,
  authority: unknown,
  base: TradingDraft = emptyTradingDraft(),
): TradingDraft {
  const cfg = (config && typeof config === "object" ? config : {}) as Record<string, unknown>;
  const auth = (authority && typeof authority === "object" ? authority : {}) as Record<string, unknown>;
  const session = (cfg.session && typeof cfg.session === "object" ? cfg.session : null) as
    | Record<string, unknown>
    | null;
  const learning = (cfg.learning && typeof cfg.learning === "object" ? cfg.learning : {}) as
    | Record<string, unknown>
    | null;
  const visuals = Array.isArray(cfg.visuals) ? (cfg.visuals as StrategyVisual[]) : [];

  const asString = (value: unknown, fallback = "") =>
    typeof value === "string" ? value : fallback;
  const asNumber = (value: unknown, fallback: number) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  };

  return {
    ...base,
    enabled: true,
    mode: (["shadow", "demo", "live"] as const).includes(cfg.mode as TradingMode)
      ? (cfg.mode as TradingMode)
      : "shadow",
    strategyId: asString(cfg.strategyId),
    strategyVersion: asString(cfg.strategyVersion),
    connectionId: asString(cfg.connectionId),
    symbolsText: parseSymbols(
      Array.isArray(cfg.symbols) ? (cfg.symbols as string[]) : [],
    ).join(", "),
    excludedText: parseSymbols(
      Array.isArray(cfg.excludedSymbols) ? (cfg.excludedSymbols as string[]) : [],
    ).join(", "),
    dynamicSymbols: cfg.dynamicSymbols === true,
    maxSymbols: asNumber(cfg.maxSymbols, base.maxSymbols),
    timeframe: asString(cfg.timeframe, base.timeframe),
    volume: asNumber(cfg.volume, base.volume),
    stopLossPoints: asNumber(cfg.stopLossPoints, base.stopLossPoints),
    takeProfitPoints: asNumber(cfg.takeProfitPoints, base.takeProfitPoints),
    maxOrdersPerDay: asNumber(cfg.maxOrdersPerDay, base.maxOrdersPerDay),
    sessionEnabled: Boolean(session),
    sessionTimezone: asString(session?.timezone, base.sessionTimezone),
    sessionStart: asString(session?.start, base.sessionStart),
    sessionEnd: asString(session?.end, base.sessionEnd),
    sessionWeekdays: Array.isArray(session?.weekdays)
      ? (session!.weekdays as number[])
      : base.sessionWeekdays,
    dryRun: cfg.dryRun === true,
    trialId: asString(cfg.trialId),
    tier: (["l0", "l1", "l2"] as const).includes(auth.tier as TradingTier)
      ? (auth.tier as TradingTier)
      : base.tier,
    appetite: (["conservative", "normal", "aggressive"] as const).includes(
      auth.appetite as RiskAppetite,
    )
      ? (auth.appetite as RiskAppetite)
      : base.appetite,
    sizingMode: auth.sizingMode === "user_fixed" ? "user_fixed" : base.sizingMode,
    requireStop: auth.requireStop !== false,
    maxOpenPositions: asNumber(auth.maxOpenPositions, base.maxOpenPositions),
    maxMarginPerOrder: asNumber(auth.maxMarginPerOrder, base.maxMarginPerOrder),
    cooldownS: asNumber(auth.cooldownS, base.cooldownS),
    maxDailyLossPct: asNumber(auth.maxDailyLossPct, base.maxDailyLossPct),
    autoMode: auth.autoMode !== false,
    autoRenew: auth.autoRenew !== false,
    learningEnabled: auth.learningEnabled !== false &&
      (learning ? learning.enabled !== false : true),
    improveAfterFailures: asNumber(
      auth.improveAfterFailures ?? learning?.threshold,
      base.improveAfterFailures,
    ),
    consent: (cfg.consent as TradingConfig["consent"]) ?? null,
    visuals,
  };
}

/** The automation action a strategy bot stores (nothing else is implied). */
export function buildTradingAction(
  draft: TradingDraft,
  objective: string,
  consent: TradingConfig["consent"] = draft.consent,
): { type: "run_strategy"; objective: string; config: TradingConfig } {
  return {
    type: "run_strategy",
    objective,
    config: buildTradingConfig(draft, consent),
  };
}

export interface TradingSummary {
  mode: string;
  tier: string;
  universe: string;
  risk: string;
  orders: string;
}

/** The one-line summary the bot header/list can render. */
export function describeTradingDraft(draft: TradingDraft): TradingSummary {
  const symbols = parseSymbols(draft.symbolsText);
  const universe = symbols.length
    ? symbols.slice(0, 3).join(", ") + (symbols.length > 3 ? ` +${symbols.length - 3}` : "")
    : "no symbols";
  return {
    mode: draft.mode,
    tier: draft.tier,
    universe,
    risk: draft.appetite,
    orders: `${draft.maxOrdersPerDay}/day`,
  };
}

/**
 * The recommended starting tier for a fresh bot: L0 (propose) for agents with no
 * track record, L1 once the operator has seen shadow decisions land. Live is
 * never a creation-time default; it is earned through `recommendTier`.
 */
export function recommendedStartTier(draft: TradingDraft, shadowDecisions = 0): TradingTier {
  if (draft.mode === "shadow") return "l0";
  return recommendTier({ mode: draft.mode, shadowDecisions, wins: 0, losses: 0 }).tier;
}
