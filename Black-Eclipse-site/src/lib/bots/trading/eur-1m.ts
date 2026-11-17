// ── EUR/USD 1-minute starter ────────────────────────────────────────────────
// One curated, honest 1-minute EUR/USD bot: the strategy spec, the bot's risk
// envelope, its schedule and the automation payload. Nothing here creates
// authority — the seed prepares a SHADOW bot; the operator authorizes demo/live
// once in the Trading panel (standing consent, no repeated phrases).
//
// Why M1 needs its own envelope: a 1-minute bar is noisy and costs matter. The
// strategy therefore uses a cross + momentum filter, an ATR stop, a 1.5R target
// and next-open fills with spread/slippage modelled. The bot caps itself at one
// position, four orders a day and a 5-minute cooldown, inside London hours.

import type { CreateAutomationInput } from "@/lib/harness/clients/automation-client";
import { localTimezone } from "@/lib/bots/state";
import {
  buildTradingAction,
  buildTradingAuthority,
  emptyTradingDraft,
  type TradingDraft,
} from "./draft";
import type { PrepareTradingInput } from "@/lib/harness/clients/automation-client";

export const EUR_1M_SYMBOL = "EURUSD";
export const EUR_1M_STRATEGY_ID = "eurusd_m1_ema_rsi";
export const EUR_1M_STRATEGY_VERSION = "1.0.0";
export const EUR_1M_BOT_NAME = "EUR/USD 1-minute scalper";
export const EUR_1M_OBJECTIVE =
  "Trade EURUSD on the 1-minute chart in London hours: enter on the EMA(9/21) " +
  "cross with RSI momentum, exit on the opposite cross or the ATR bracket. " +
  "One position at a time, hard stop on every order, and never trade outside " +
  "the configured session.";

/**
 * The strategy spec. Shape follows the quant strategy contract
 * (`src/lib/backtest/backtest-client.ts` + `python/harness/quant/strategy.py`):
 * timeframe ids are the engine's (`1m`), not the bot's (`M1`).
 */
export const EUR_1M_STRATEGY_SPEC: Record<string, unknown> = {
  strategy: {
    id: EUR_1M_STRATEGY_ID,
    name: "EUR/USD 1m EMA-RSI",
    version: EUR_1M_STRATEGY_VERSION,
    description:
      "EURUSD 1-minute EMA(9/21) cross with RSI momentum, ATR stop and 1.5R target.",
  },
  universe: { symbols: [EUR_1M_SYMBOL], asset_classes: ["fx"] },
  timeframes: { primary: "1m", confirmation: [] },
  indicators: [
    { id: "ema_fast", type: "ema", params: { period: 9 } },
    { id: "ema_slow", type: "ema", params: { period: 21 } },
    { id: "rsi", type: "rsi", params: { period: 14 } },
    { id: "atr", type: "atr", params: { period: 14 } },
  ],
  rules: {
    entry: {
      long: {
        type: "group",
        combine: "all",
        conditions: [
          { type: "condition", left: { ref: "ema_fast" }, op: "cross_above", right: { ref: "ema_slow" } },
          { type: "condition", left: { ref: "rsi" }, op: ">", right: { value: 50 } },
        ],
      },
      short: {
        type: "group",
        combine: "all",
        conditions: [
          { type: "condition", left: { ref: "ema_fast" }, op: "cross_below", right: { ref: "ema_slow" } },
          { type: "condition", left: { ref: "rsi" }, op: "<", right: { value: 50 } },
        ],
      },
    },
    exit: {
      long: {
        type: "group",
        combine: "any",
        conditions: [
          { type: "condition", left: { ref: "ema_fast" }, op: "cross_below", right: { ref: "ema_slow" } },
          { type: "condition", left: { ref: "rsi" }, op: "<", right: { value: 45 } },
        ],
      },
      short: {
        type: "group",
        combine: "any",
        conditions: [
          { type: "condition", left: { ref: "ema_fast" }, op: "cross_above", right: { ref: "ema_slow" } },
          { type: "condition", left: { ref: "rsi" }, op: ">", right: { value: 55 } },
        ],
      },
      stop_loss: { type: "atr", value: 1.5 },
      take_profit: { type: "risk_reward", value: 1.5 },
    },
  },
  position_sizing: { type: "percent_risk", value: 0.5 },
  risk: {
    max_position_pct: 10,
    max_open_positions: 1,
    max_daily_loss_pct: 3,
    max_risk_per_trade_pct: 0.5,
    allow_long: true,
    allow_short: true,
  },
  execution: {
    // 1-minute FX: the spread is the dominant cost. Modelled explicitly so a
    // backtest is not flattered.
    commission: { type: "none", value: 0 },
    slippage: { type: "percentage", value: 0.001 },
    spread: { type: "bps", value: 1.2 },
    fill_at: "next_open",
  },
  metadata: {
    starter: "eur-1m",
    rationale:
      "A 1-minute cross without a momentum filter whipsaws; RSI is used only as a " +
      "veto, and the ATR bracket defines risk per trade.",
    notFinancialAdvice: true,
  },
};

/** The bot's trading envelope (shadow until the operator authorizes). */
export function eur1mTradingDraft(): TradingDraft {
  return {
    ...emptyTradingDraft(),
    enabled: true,
    mode: "shadow",
    strategyId: EUR_1M_STRATEGY_ID,
    strategyVersion: EUR_1M_STRATEGY_VERSION,
    symbolsText: EUR_1M_SYMBOL,
    dynamicSymbols: false,
    maxSymbols: 1,
    timeframe: "M1",
    volume: 0.01,
    stopLossPoints: 30,
    takeProfitPoints: 45,
    maxOrdersPerDay: 4,
    sessionEnabled: true,
    sessionTimezone: "Europe/London",
    sessionStart: "08:00",
    sessionEnd: "17:00",
    sessionWeekdays: [1, 2, 3, 4, 5],
    dryRun: false,
    // L1 so the operator can authorize a DEMO account immediately; LIVE still
    // needs an explicit L2 raise plus an armed connection and a mandate.
    tier: "l1",
    appetite: "normal",
    requireStop: true,
    maxOpenPositions: 1,
    maxMarginPerOrder: 100,
    cooldownS: 300,
    maxDailyLossPct: 3,
    autoMode: true,
    autoRenew: true,
    learningEnabled: true,
    improveAfterFailures: 3,
  };
}

/** The automation the seed creates (a draft; prepare + activation follow). */
export function eur1mAutomationInput(
  strategyId: string = EUR_1M_STRATEGY_ID,
  strategyVersion: string = EUR_1M_STRATEGY_VERSION,
): CreateAutomationInput {
  const draft = { ...eur1mTradingDraft(), strategyId, strategyVersion };
  return {
    name: EUR_1M_BOT_NAME,
    description: "EURUSD on 1-minute bars, London hours, one position at a time.",
    state: "draft",
    // A 1-minute bot wakes every minute and acts on the last CLOSED bar; the
    // runner claims a bar once, so a duplicate wake cannot double-trade.
    trigger: { type: "interval", intervalSeconds: 60, timezone: localTimezone() },
    action: {
      type: "run_strategy",
      objective: EUR_1M_OBJECTIVE,
      config: buildTradingAction(draft, EUR_1M_OBJECTIVE, null)
        .config as unknown as Record<string, unknown>,
    },
    executionAuthority: buildTradingAuthority(draft),
    execution: { misfire: "skip", maxRuntimeS: 120 },
    concurrency: { maxConcurrentRuns: 1, onConflict: "skip_if_running" },
    retry: { maxAttempts: 1 },
    tags: ["bot", "trading", "eur-1m"],
  };
}

/** The prepare payload for the shadow trial (no consent, no broker writes). */
export function eur1mPrepareInput(
  strategyId: string = EUR_1M_STRATEGY_ID,
  strategyVersion: string = EUR_1M_STRATEGY_VERSION,
): PrepareTradingInput {
  return {
    strategyId,
    strategyVersion,
    mode: "shadow",
    connectionId: "",
    symbols: [EUR_1M_SYMBOL],
    timeframe: "M1",
    volume: 0.01,
    stopLossPoints: 30,
    takeProfitPoints: 45,
    maxOrders: 4,
    maxMargin: 100,
    confirmation: "",
  };
}
