// ── Journal analytics — public API ───────────────────────────────────────────
// Aggregates all deterministic analytics into a single consumable object that
// the UI and the future Agentic Harness can both use.

import type { JournalAnalytics, TradeRecord } from "../types";
import { computePerformance } from "./performance";
import { aggregateDays } from "./calendar";
import { computeDiscipline } from "./discipline";
import {
  bySymbol,
  byStrategy,
  bySetup,
  bySession,
  byDirection,
  byDayOfWeek,
  byHour,
  byTimeframe,
  byRegime,
  byTrend,
  byAccount,
  byMagic,
  byEmotion,
} from "./dimensions";
import { byConfidence, confidenceCorrelation } from "./psychology";
import {
  monthlyReturns,
  rollingPerformance,
  mfeMaeScatter,
  confidenceScatter,
  durationBuckets,
  currencyEquity,
  accountSummaries,
  riskAlerts,
  yearReports,
} from "./advanced";

export * from "./performance";
export * from "./dimensions";
export * from "./calendar";
export * from "./discipline";
export * from "./psychology";
export * from "./weekly";
export * from "./wrapped";
export * from "./mfe-mae";
export * from "./market-context";
export * from "./similarity";
export * from "./advanced";

export interface AnalyticsOptions {
  accountSize?: number | null;
  riskPerTrade?: number | null;
  accounts?: { id: string; name: string; broker?: string | null; currency: string; initialBalance: number }[];
}

/** Compute the full analytics bundle for a set of trades. */
export function computeJournalAnalytics(trades: TradeRecord[], options: AnalyticsOptions = {}): JournalAnalytics {
  const performance = computePerformance(trades);
  const days = aggregateDays(trades);

  // Equity curve from performance (recompute for the chart-friendly shape).
  const sorted = [...trades]
    .filter((t) => t.status === "closed")
    .sort((a, b) => Date.parse(a.exitTime) - Date.parse(b.exitTime));
  let equity = 0;
  let peak = 0;
  const equityCurve = sorted.map((t) => {
    equity += t.rMultiple;
    if (equity > peak) peak = equity;
    return { date: t.exitTime, equity, drawdown: peak - equity };
  });

  return {
    performance,
    equity: equityCurve,
    bySymbol: bySymbol(trades),
    byStrategy: byStrategy(trades),
    bySetup: bySetup(trades),
    bySession: bySession(trades),
    byDirection: byDirection(trades),
    byDayOfWeek: byDayOfWeek(trades),
    byHour: byHour(trades),
    byTimeframe: byTimeframe(trades),
    byRegime: byRegime(trades),
    byTrend: byTrend(trades),
    byAccount: byAccount(trades),
    byMagic: byMagic(trades),
    byEmotion: byEmotion(trades),
    byConfidence: byConfidence(trades),
    confidenceCorrelation: confidenceCorrelation(trades),
    discipline: computeDiscipline(trades, { accountSize: options.accountSize, riskPerTrade: options.riskPerTrade }),
    days,
    monthlyReturns: monthlyReturns(trades),
    rolling: rollingPerformance(trades),
    mfeMae: mfeMaeScatter(trades),
    confidenceScatter: confidenceScatter(trades),
    durationBuckets: durationBuckets(trades),
    equityCurrency: currencyEquity(trades, options.accountSize),
    accounts: accountSummaries(trades, options.accounts ?? []),
    riskAlerts: riskAlerts(trades, { accountSize: options.accountSize, riskPerTrade: options.riskPerTrade }),
    yearReports: yearReports(trades),
  };
}
