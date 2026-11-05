// ── Trade math — deterministic P&L / R-multiple calculations ─────────────────
// Pure functions. Never user-entered; the API computes these on save.

import type { Direction } from "./types";

export interface TradeInput {
  direction: Direction;
  entry: number;
  /** Null while the position is open. */
  exit: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: string;
  exitTime: string;
  /** Round-turn commission in account currency (optional, defaults 0). */
  commission?: number | null;
  /** Other fees / swap / financing (optional, defaults 0). */
  fee?: number | null;
}

export interface TradeMath {
  /** Gross P&L before costs. */
  grossPnl: number;
  /** Total costs (commission + fee). */
  fees: number;
  /** Net P&L = grossPnl − fees. This is the value stored as Trade.pnl. */
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  riskAmount: number | null;
  rewardAmount: number | null;
  actualRR: number | null;
  durationSec: number | null;
}

/** Signed P&L in account currency. */
export function computePnl(direction: Direction, entry: number, exit: number, quantity: number): number {
  const sign = direction === "LONG" ? 1 : -1;
  return (exit - entry) * sign * quantity;
}

/** P&L as a fraction of the entry notional. */
export function computePnlPct(direction: Direction, entry: number, exit: number): number {
  if (!entry) return 0;
  const sign = direction === "LONG" ? 1 : -1;
  return ((exit - entry) * sign) / entry;
}

/** Risk per unit (entry→stop distance, signed by direction). */
export function riskPerUnit(direction: Direction, entry: number, stopLoss: number | null): number | null {
  if (stopLoss == null) return null;
  const sign = direction === "LONG" ? 1 : -1;
  return (entry - stopLoss) * sign;
}

/** Reward per unit (target→entry distance, signed by direction). */
export function rewardPerUnit(direction: Direction, entry: number, takeProfit: number | null): number | null {
  if (takeProfit == null) return null;
  const sign = direction === "LONG" ? 1 : -1;
  return (takeProfit - entry) * sign;
}

/** R-multiple = realized P&L / risk. Null risk → 0. */
export function computeRMultiple(pnl: number, riskAmount: number | null): number {
  if (!riskAmount) return 0;
  return pnl / riskAmount;
}

/** Full deterministic trade math. */
export function computeTradeMath(input: TradeInput): TradeMath {
  const { direction, entry, exit, stopLoss, takeProfit, quantity, entryTime, exitTime } = input;
  const isOpen = exit == null;
  const grossPnl = isOpen ? 0 : computePnl(direction, entry, exit, quantity);
  // Costs only bite once the position is closed.
  const fees = isOpen ? 0 : (input.commission ?? 0) + (input.fee ?? 0);
  const pnl = grossPnl - fees;
  const pnlPct = isOpen ? 0 : computePnlPct(direction, entry, exit);
  const riskPerUnitVal = riskPerUnit(direction, entry, stopLoss);
  const rewardPerUnitVal = rewardPerUnit(direction, entry, takeProfit);
  const riskAmount = riskPerUnitVal != null ? riskPerUnitVal * quantity : null;
  const rewardAmount = rewardPerUnitVal != null ? rewardPerUnitVal * quantity : null;
  const rMultiple = isOpen ? 0 : computeRMultiple(pnl, riskAmount);
  const actualRR = riskPerUnitVal != null && rewardPerUnitVal != null && riskPerUnitVal !== 0
    ? rewardPerUnitVal / riskPerUnitVal
    : null;
  const durationSec = (() => {
    if (isOpen) return null;
    const a = Date.parse(entryTime);
    const b = Date.parse(exitTime);
    if (Number.isNaN(a) || Number.isNaN(b)) return null;
    return Math.max(0, Math.round((b - a) / 1000));
  })();

  return { grossPnl, fees, pnl, pnlPct, rMultiple, riskAmount, rewardAmount, actualRR, durationSec };
}

/** Classify a trade result by R-multiple. */
export function classifyResult(r: number): "win" | "loss" | "breakeven" {
  if (r > 0) return "win";
  if (r < 0) return "loss";
  return "breakeven";
}

/**
 * True when the trade carries a usable R basis (a stop loss was known and the
 * risk per unit is positive). Broker-imported trades almost never have one —
 * MT5 deal history does not carry SL — so R metrics are unavailable for them.
 */
export function hasRBasis(t: { riskAmount: number | null }): boolean {
  return t.riskAmount != null && t.riskAmount > 0;
}

/**
 * Outcome classification with an honest fallback: R when the trade has a risk
 * basis, otherwise the sign of the net P&L. A +$53.60 trade is a win even
 * though no stop was captured; a −$0.79 trade is a loss. Breakeven requires an
 * exactly-zero result on the basis in use.
 */
export function classifyTradeOutcome(t: {
  rMultiple: number;
  riskAmount: number | null;
  pnl: number;
}): "win" | "loss" | "breakeven" {
  if (hasRBasis(t)) return classifyResult(t.rMultiple);
  if (t.pnl > 0) return "win";
  if (t.pnl < 0) return "loss";
  return "breakeven";
}

/**
 * R is measurable only for a CLOSED trade with a positive risk basis. An open
 * position may carry a stop from the broker snapshot, but its R is unrealized,
 * so it must not render as `+0.00R`.
 */
export function isRMeasurable(t: { riskAmount: number | null; status?: string | null }): boolean {
  return t.status !== "open" && hasRBasis(t);
}
