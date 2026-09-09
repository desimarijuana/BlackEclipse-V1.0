// ── Performance analytics — deterministic trading statistics ─────────────────
// Pure functions over TradeRecord[]. No LLM, no randomness. Every metric is
// derived from structured trade data so results are reproducible.

import type { PerformanceStats, TradeRecord } from "../types";
import { classifyResult } from "../trade-math";

/** Sort trades chronologically by exit time. */
export function sortTrades(trades: TradeRecord[]): TradeRecord[] {
  return [...trades].sort((a, b) => Date.parse(a.exitTime) - Date.parse(b.exitTime));
}

/** Compute the full performance stats for a set of trades. */
export function computePerformance(trades: TradeRecord[]): PerformanceStats {
  const closed = trades.filter((t) => t.status === "closed");
  const n = closed.length;

  const wins = closed.filter((t) => classifyResult(t.rMultiple) === "win");
  const losses = closed.filter((t) => classifyResult(t.rMultiple) === "loss");
  const breakevens = closed.filter((t) => classifyResult(t.rMultiple) === "breakeven");

  const winRate = n > 0 ? wins.length / n : 0;
  const averageWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
  const averageLoss = losses.length > 0 ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0;
  const netPnl = closed.reduce((s, t) => s + t.pnl, 0);
  const netR = closed.reduce((s, t) => s + t.rMultiple, 0);
  const expectancy = n > 0 ? netR / n : 0;
  const averageR = n > 0 ? netR / n : 0;

  // Profit factor = gross wins / gross losses (in R).
  const grossWinR = wins.reduce((s, t) => s + t.rMultiple, 0);
  const grossLossR = Math.abs(losses.reduce((s, t) => s + t.rMultiple, 0));
  const profitFactor = grossLossR > 0 ? grossWinR / grossLossR : grossWinR > 0 ? Infinity : 0;

  // Equity curve (cumulative R) + max drawdown + recovery factor.
  const sorted = sortTrades(closed);
  let equity = 0;
  let peak = 0;
  let maxDrawdown = 0;
  const equityCurve: { date: string; equity: number; drawdown: number }[] = [];
  for (const t of sorted) {
    equity += t.rMultiple;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDrawdown) maxDrawdown = dd;
    equityCurve.push({ date: t.exitTime, equity, drawdown: dd });
  }
  const recoveryFactor = maxDrawdown > 0 ? netR / maxDrawdown : netR > 0 ? Infinity : 0;

  // Streaks (chronological).
  let winningStreak = 0;
  let losingStreak = 0;
  let currentStreak = 0;
  let cur = 0;
  for (const t of sorted) {
    const cls = classifyResult(t.rMultiple);
    if (cls === "win") {
      cur = cur > 0 ? cur + 1 : 1;
      if (cur > winningStreak) winningStreak = cur;
    } else if (cls === "loss") {
      cur = cur < 0 ? cur - 1 : -1;
      if (-cur > losingStreak) losingStreak = -cur;
    } else {
      cur = 0;
    }
  }
  currentStreak = cur;

  // Risk metrics.
  const risks = closed.map((t) => t.riskAmount).filter((v): v is number => v != null && v > 0);
  const averageRisk = risks.length > 0 ? risks.reduce((s, v) => s + v, 0) / risks.length : 0;
  const riskStd = risks.length > 1
    ? Math.sqrt(risks.reduce((s, v) => s + (v - averageRisk) ** 2, 0) / (risks.length - 1))
    : 0;
  const riskConsistency = averageRisk > 0 ? 1 - Math.min(1, riskStd / averageRisk) : 0;
  const largestRisk = risks.length > 0 ? Math.max(...risks) : 0;

  // Risk violations: trades whose risk exceeds the account default (1%).
  // We approximate using the trade's own riskAmount vs a 1% notional proxy.
  const riskViolations = closed.filter((t) => {
    if (t.riskAmount == null) return false;
    const notional = t.entry * t.quantity;
    return notional > 0 && t.riskAmount / notional > 0.01;
  }).length;

  // Stop / target distances (as % of entry).
  const stopDists = closed
    .map((t) => (t.stopLoss != null && t.entry !== 0 ? Math.abs((t.entry - t.stopLoss) / t.entry) : null))
    .filter((v): v is number => v != null);
  const targetDists = closed
    .map((t) => (t.takeProfit != null && t.entry !== 0 ? Math.abs((t.takeProfit - t.entry) / t.entry) : null))
    .filter((v): v is number => v != null);
  const averageStopDistance = stopDists.length > 0 ? stopDists.reduce((s, v) => s + v, 0) / stopDists.length : 0;
  const averageTargetDistance = targetDists.length > 0 ? targetDists.reduce((s, v) => s + v, 0) / targetDists.length : 0;

  // Planned vs realized R:R.
  const plannedRRs = closed
    .map((t) => {
      if (t.stopLoss == null || t.takeProfit == null || t.entry === 0) return null;
      const risk = Math.abs((t.entry - t.stopLoss) / t.entry);
      const reward = Math.abs((t.takeProfit - t.entry) / t.entry);
      return risk > 0 ? reward / risk : null;
    })
    .filter((v): v is number => v != null);
  const averagePlannedRR = plannedRRs.length > 0 ? plannedRRs.reduce((s, v) => s + v, 0) / plannedRRs.length : 0;
  const realizedRRs = closed.map((t) => t.actualRR).filter((v): v is number => v != null);
  const averageRealizedRR = realizedRRs.length > 0 ? realizedRRs.reduce((s, v) => s + v, 0) / realizedRRs.length : 0;

  // Execution metrics.
  const durations = closed.map((t) => t.durationSec).filter((v): v is number => v != null);
  const averageDurationSec = durations.length > 0 ? durations.reduce((s, v) => s + v, 0) / durations.length : 0;
  const mfes = closed.map((t) => t.mfe).filter((v): v is number => v != null);
  const maes = closed.map((t) => t.mae).filter((v): v is number => v != null);
  const averageMfe = mfes.length > 0 ? mfes.reduce((s, v) => s + v, 0) / mfes.length : 0;
  const averageMae = maes.length > 0 ? maes.reduce((s, v) => s + v, 0) / maes.length : 0;

  // Behavioral flags (from mistakes JSON).
  const earlyExits = closed.filter((t) => hasMistake(t, "early")).length;
  const stopModifications = closed.filter((t) => hasMistake(t, "stop")).length;
  const targetModifications = closed.filter((t) => hasMistake(t, "target")).length;
  const partialExits = closed.filter((t) => hasMistake(t, "partial")).length;

  // Sharpe / Sortino (daily R returns).
  const dailyReturns = aggregateDailyR(sorted);
  const { sharpe, sortino } = computeRatios(dailyReturns);

  return {
    totalTrades: n,
    wins: wins.length,
    losses: losses.length,
    breakevens: breakevens.length,
    winRate,
    averageWin,
    averageLoss,
    netPnl,
    netR,
    expectancy,
    profitFactor,
    averageR,
    maxDrawdown,
    recoveryFactor,
    sharpe,
    sortino,
    winningStreak,
    losingStreak,
    currentStreak,
    averageRisk,
    riskConsistency,
    largestRisk,
    riskViolations,
    averageStopDistance,
    averageTargetDistance,
    averagePlannedRR,
    averageRealizedRR,
    averageDurationSec,
    averageMfe,
    averageMae,
    earlyExits,
    stopModifications,
    targetModifications,
    partialExits,
  };
}

function hasMistake(t: TradeRecord, keyword: string): boolean {
  if (!t.mistakes) return false;
  try {
    const arr = JSON.parse(t.mistakes) as string[];
    return arr.some((m) => m.toLowerCase().includes(keyword));
  } catch {
    return false;
  }
}

/** Aggregate per-day net R for Sharpe/Sortino. */
function aggregateDailyR(trades: TradeRecord[]): number[] {
  const byDay = new Map<string, number>();
  for (const t of trades) {
    const day = t.exitTime.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + t.rMultiple);
  }
  return [...byDay.values()];
}

function computeRatios(returns: number[]): { sharpe: number | null; sortino: number | null } {
  if (returns.length < 2) return { sharpe: null, sortino: null };
  const mean = returns.reduce((s, v) => s + v, 0) / returns.length;
  const variance = returns.reduce((s, v) => s + (v - mean) ** 2, 0) / (returns.length - 1);
  const std = Math.sqrt(variance);
  const sharpe = std > 0 ? mean / std : null;
  const downside = returns.filter((v) => v < 0);
  const downsideDev = downside.length > 0
    ? Math.sqrt(downside.reduce((s, v) => s + v ** 2, 0) / downside.length)
    : 0;
  const sortino = downsideDev > 0 ? mean / downsideDev : null;
  return { sharpe, sortino };
}
