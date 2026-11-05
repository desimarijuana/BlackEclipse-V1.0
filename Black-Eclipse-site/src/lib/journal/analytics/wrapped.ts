// ── Monthly Trading Wrapped — polished monthly performance report ────────────
// Deterministic: best setup/market/session, biggest leak, discipline. All
// facts computed from the analytics engine.

import type { DimensionRow, TradeRecord } from "../types";
import { computePerformance } from "./performance";
import { computeDiscipline } from "./discipline";
import { bySymbol, bySetup, bySession, byHour } from "./dimensions";
import { biggestLeak, byConfidence, confidenceCorrelation } from "./psychology";

export interface MonthlyWrapped {
  year: number;
  month: number; // 0-indexed
  label: string;
  performance: {
    trades: number;
    winRate: number;
    netR: number;
    netPnl: number;
    profitFactor: number;
    expectancy: number;
    maxDrawdown: number;
    /** False when no trade in the month carried a stop-derived R basis. */
    rAvailable: boolean;
  };
  bestSetup: DimensionRow | null;
  bestMarket: DimensionRow | null;
  bestSession: DimensionRow | null;
  bestHour: DimensionRow | null;
  biggestLeak: DimensionRow | null;
  bestConfidence: DimensionRow | null;
  confidenceCorrelation: number | null;
  discipline: number;
}

export function buildMonthlyWrapped(trades: TradeRecord[], year: number, month: number): MonthlyWrapped {
  const prefix = `${year}-${String(month + 1).padStart(2, "0")}`;
  const range = trades.filter((t) => t.status === "closed" && t.exitTime.startsWith(prefix));
  const perf = computePerformance(range);
  const symbols = bySymbol(range);
  const setups = bySetup(range);
  const sessions = bySession(range);
  const hours = byHour(range);
  const confidence = byConfidence(range);

  return {
    year,
    month,
    label: new Date(Date.UTC(year, month, 1)).toLocaleString("en", { month: "long", year: "numeric" }),
    performance: {
      trades: perf.totalTrades,
      winRate: perf.winRate,
      netR: perf.netR,
      netPnl: perf.netPnl,
      profitFactor: perf.profitFactor,
      expectancy: perf.expectancy,
      maxDrawdown: perf.maxDrawdown,
      rAvailable: perf.rAvailable,
    },
    bestSetup: setups.length > 0 ? setups[0] : null,
    bestMarket: symbols.length > 0 ? symbols[0] : null,
    bestSession: sessions.length > 0 ? sessions[0] : null,
    bestHour: hours.length > 0 ? hours[0] : null,
    biggestLeak: biggestLeak(range),
    bestConfidence: confidence.length > 0 ? confidence[0] : null,
    confidenceCorrelation: confidenceCorrelation(range),
    discipline: perf.totalTrades > 0 ? computeDiscipline(range).total : 0,
  };
}

/** Build the wrapped report for the current month. */
export function buildCurrentMonthWrapped(trades: TradeRecord[]): MonthlyWrapped {
  const now = new Date();
  return buildMonthlyWrapped(trades, now.getUTCFullYear(), now.getUTCMonth());
}
