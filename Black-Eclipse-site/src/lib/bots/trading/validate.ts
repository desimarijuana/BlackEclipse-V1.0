// ── Trading setup validation (client mirror) ────────────────────────────────
// The server is the authority (`automation/validation.py`); this module mirrors
// the rules so the operator sees the same error beside the same field. Keep the
// codes identical — a test asserts the two lists do not drift.

import { APPETITE_BANDS, MAX_MAX_ORDERS_PER_DAY, TIMEFRAME_MS } from "./types";
import { consentCovers } from "./consent";
import { parseSymbols, resolveTradable } from "./symbols";
import type {
  TradingAuthority,
  TradingConfig,
  TradingMode,
} from "./types";

export type IssueSeverity = "error" | "warning";

export interface TradingIssue {
  field: string;
  code: string;
  message: string;
  severity: IssueSeverity;
}

export interface StrategyOption {
  id: string;
  name?: string;
  version?: string;
  /** A completed backtest exists for this version. */
  hasBacktest?: boolean;
  /** An approval exists for this version. */
  approved?: boolean;
}

export interface ConnectionOption {
  id: string;
  label: string;
  /** `demo` | `live` | `unknown` */
  mode: string;
  /** ISO instant while a live connection is armed. */
  armedUntil?: string | null;
  /** Symbols the venue offers, when already known. */
  symbols?: string[];
}

export interface TradingContext {
  strategies: readonly StrategyOption[];
  connections: readonly ConnectionOption[];
  /** Symbols the selected venue offers; absent means "not loaded yet". */
  venueSymbols?: readonly string[] | null;
  now?: number;
}

/** Every refusal code this layer can produce (server mirror). */
export const TRADING_ISSUE_CODES: readonly string[] = [
  "STRATEGY_ID_REQUIRED",
  "STRATEGY_VERSION_REQUIRED",
  "STRATEGY_UNAVAILABLE",
  "STRATEGY_NO_BACKTEST",
  "STRATEGY_NOT_APPROVED",
  "INVALID_TRADING_MODE",
  "CONNECTION_REQUIRED",
  "CONNECTION_UNAVAILABLE",
  "MODE_MISMATCH",
  "SYMBOLS_REQUIRED",
  "SYMBOL_NOT_TRADABLE",
  "INVALID_TIMEFRAME",
  "VOLUME_REQUIRED",
  "STOP_REQUIRED",
  "BOT_TIER_REQUIRED",
  "LIVE_NOT_ARMED",
  "CONSENT_REQUIRED",
  "CONSENT_EXPIRED",
  "CONSENT_REVOKED",
  "ORDERS_ABOVE_BAND",
  "POSITIONS_ABOVE_BAND",
  "LEARNING_THRESHOLD_RANGE",
  "CONNECTION_MODE_UNKNOWN",
  "VISUAL_CAPTION_MISSING",
];

export function selectedStrategy(
  config: Pick<TradingConfig, "strategyId" | "strategyVersion">,
  strategies: readonly StrategyOption[],
): StrategyOption | undefined {
  return strategies.find(
    (item) =>
      item.id === config.strategyId &&
      (!item.version || !config.strategyVersion || item.version === config.strategyVersion),
  );
}

export function selectedConnection(
  config: Pick<TradingConfig, "connectionId">,
  connections: readonly ConnectionOption[],
): ConnectionOption | undefined {
  return connections.find((item) => item.id === config.connectionId);
}

/**
 * Validate a full trading setup. Errors block saving/preparing; warnings are
 * shown but do not.
 */
export function validateTradingSetup(
  config: TradingConfig,
  authority: TradingAuthority,
  context: TradingContext,
  options: { requireStrategy?: boolean } = {},
): TradingIssue[] {
  const issues: TradingIssue[] = [];
  const now = context.now ?? Date.now();
  const requireStrategy = options.requireStrategy !== false;
  const add = (
    severity: IssueSeverity,
    code: string,
    field: string,
    message: string,
  ) => issues.push({ severity, code, field, message });

  // ── Strategy pin ──────────────────────────────────────────────────────────
  if (requireStrategy) {
    if (!String(config.strategyId ?? "").trim()) {
      add("error", "STRATEGY_ID_REQUIRED", "strategyId", "Choose the strategy this bot should trade.");
    }
    if (!String(config.strategyVersion ?? "").trim()) {
      add("error", "STRATEGY_VERSION_REQUIRED", "strategyVersion", "Choose the strategy version.");
    }
    if (config.strategyId) {
      const strategy = selectedStrategy(config, context.strategies);
      if (!strategy) {
        add(
          "error",
          "STRATEGY_UNAVAILABLE",
          "strategyId",
          "That strategy version is not available. Pick another version or re-save the strategy.",
        );
      } else {
        if (strategy.hasBacktest === false) {
          add(
            "warning",
            "STRATEGY_NO_BACKTEST",
            "strategyId",
            "This version has no completed backtest. The server refuses trading until it does.",
          );
        }
        if (strategy.approved === false) {
          add(
            "warning",
            "STRATEGY_NOT_APPROVED",
            "strategyId",
            "This version is not approved yet. Approve it in Strategy Studio before enabling live trading.",
          );
        }
      }
    }
  }

  // ── Mode + venue ──────────────────────────────────────────────────────────
  const modes: TradingMode[] = ["shadow", "demo", "live"];
  if (!modes.includes(config.mode)) {
    add("error", "INVALID_TRADING_MODE", "mode", "Choose shadow, demo or live.");
  }
  const connection = selectedConnection(config, context.connections);
  if (config.mode !== "shadow") {
    if (!config.connectionId) {
      add("error", "CONNECTION_REQUIRED", "connectionId", "Choose the broker connection.");
    } else if (!connection) {
      add("error", "CONNECTION_UNAVAILABLE", "connectionId", "That connection no longer exists.");
    } else {
      if (connection.mode === "unknown") {
        add(
          "error",
          "CONNECTION_MODE_UNKNOWN",
          "connectionId",
          "This connection has no execution mode. Set it to demo or live in Settings › Trading.",
        );
      } else if (connection.mode !== config.mode) {
        add(
          "error",
          "MODE_MISMATCH",
          "mode",
          `This bot is ${config.mode} but the connection is ${connection.mode}.`,
        );
      }
      if (config.mode === "live") {
        const armed = connection.armedUntil
          ? new Date(connection.armedUntil).getTime() > now
          : false;
        if (!armed) {
          add("error", "LIVE_NOT_ARMED", "connectionId", "Arm the live connection first.");
        }
        if (authority.tier !== "l2") {
          add(
            "error",
            "BOT_TIER_REQUIRED",
            "tier",
            "Live execution needs tier L2. Raise the tier once the bot has a track record.",
          );
        }
      }
      if (config.mode === "demo" && !config.dryRun && authority.tier === "l0") {
        add(
          "warning",
          "BOT_TIER_REQUIRED",
          "tier",
          "Tier L0 only proposes. Use preview (dry run) or raise the tier to L1 to fill a demo account.",
        );
      }
    }
  }

  // ── Universe ──────────────────────────────────────────────────────────────
  const symbols = parseSymbols(config.symbols);
  if (!symbols.length) {
    add("error", "SYMBOLS_REQUIRED", "symbols", "Add at least one symbol.");
  }
  if (context.venueSymbols && context.venueSymbols.length && config.mode !== "shadow") {
    const { missing } = resolveTradable(symbols, context.venueSymbols);
    if (missing.length) {
      add(
        "error",
        "SYMBOL_NOT_TRADABLE",
        "symbols",
        `${missing.join(", ")} ${missing.length === 1 ? "is" : "are"} not offered by this venue.`,
      );
    }
  }

  // ── Timeframe + size ──────────────────────────────────────────────────────
  if (!TIMEFRAME_MS[String(config.timeframe).toUpperCase()]) {
    add("error", "INVALID_TIMEFRAME", "timeframe", "Choose a supported timeframe.");
  }
  if (!(Number(config.volume) > 0)) {
    add("error", "VOLUME_REQUIRED", "volume", "Order volume must be greater than zero.");
  }
  if (authority.requireStop && !(Number(config.stopLossPoints) > 0)) {
    add(
      "error",
      "STOP_REQUIRED",
      "stopLossPoints",
      "This bot requires a stop loss, so set a stop distance.",
    );
  }

  // ── Band ceilings ─────────────────────────────────────────────────────────
  const band = APPETITE_BANDS[authority.appetite] ?? APPETITE_BANDS.normal;
  if (config.maxOrdersPerDay > Math.min(band.maxOrdersPerDay, MAX_MAX_ORDERS_PER_DAY)) {
    add(
      "error",
      "ORDERS_ABOVE_BAND",
      "maxOrdersPerDay",
      `${authority.appetite} allows at most ${band.maxOrdersPerDay} orders/day.`,
    );
  }
  if (authority.maxOpenPositions > band.maxPositions) {
    add(
      "error",
      "POSITIONS_ABOVE_BAND",
      "maxOpenPositions",
      `${authority.appetite} allows at most ${band.maxPositions} open position(s).`,
    );
  }
  if (authority.improveAfterFailures < 2 || authority.improveAfterFailures > 10) {
    add(
      "error",
      "LEARNING_THRESHOLD_RANGE",
      "improveAfterFailures",
      "Ask me after 2–10 repeated failures.",
    );
  }

  // ── Consent (the auto mode) ───────────────────────────────────────────────
  if (config.mode !== "shadow" && !config.dryRun) {
    const request = {
      mode: config.mode,
      symbols,
      maxOrdersPerDay: config.maxOrdersPerDay,
      maxMarginPerOrder: authority.maxMarginPerOrder,
      maxOpenPositions: authority.maxOpenPositions,
    };
    const check = consentCovers(config.consent, request, now);
    if (!check.covered) {
      const code = !config.consent
        ? "CONSENT_REQUIRED"
        : check.status === "revoked"
          ? "CONSENT_REVOKED"
          : check.status === "expired"
            ? "CONSENT_EXPIRED"
            : "CONSENT_REQUIRED";
      add("error", code, check.field ?? "consent", check.reason ?? "Grant trading consent.");
    }
  }

  // ── Visual teaching ───────────────────────────────────────────────────────
  for (const [index, visual] of config.visuals.entries()) {
    if (!visual.caption.trim()) {
      add(
        "warning",
        "VISUAL_CAPTION_MISSING",
        `visuals.${index}`,
        "Add a caption so the bot knows what this picture teaches.",
      );
    }
  }

  return issues;
}

export interface EffectiveEnvelope {
  tier: string;
  mode: TradingMode;
  riskPerTradePct: number;
  maxPositions: number;
  maxOrdersPerDay: number;
  maxMarginPerOrder: number;
  cooldownS: number;
  requireStop: boolean;
}

/** The limits that will actually apply: the strictest of band, bot and mandate. */
export function effectiveEnvelope(
  config: TradingConfig,
  authority: TradingAuthority,
): EffectiveEnvelope {
  const band = APPETITE_BANDS[authority.appetite] ?? APPETITE_BANDS.normal;
  const consentCap = config.consent?.limits.maxMarginPerOrder ?? 0;
  const marginCaps = [authority.maxMarginPerOrder, consentCap].filter((n) => n > 0);
  return {
    tier: authority.tier,
    mode: config.mode,
    riskPerTradePct: band.riskPerTradePct,
    maxPositions: Math.min(authority.maxOpenPositions, band.maxPositions),
    maxOrdersPerDay: Math.min(config.maxOrdersPerDay, band.maxOrdersPerDay),
    maxMarginPerOrder: marginCaps.length ? Math.min(...marginCaps) : 0,
    cooldownS: authority.cooldownS,
    requireStop: authority.requireStop,
  };
}

export function errorsOnly(issues: readonly TradingIssue[]): TradingIssue[] {
  return issues.filter((issue) => issue.severity === "error");
}

export function hasBlockingIssues(issues: readonly TradingIssue[]): boolean {
  return issues.some((issue) => issue.severity === "error");
}
