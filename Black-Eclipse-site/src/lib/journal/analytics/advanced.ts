// ── Advanced analytics — depth metrics (Phase 4) ─────────────────────────────
// Pure functions adding the deeper cuts a serious journal needs: monthly
// returns, rolling performance, MAE/MFE efficiency, confidence-vs-outcome
// scatter, duration buckets and currency-denominated equity. No LLM, no
// randomness — every value is derived deterministically from trade records.

import type {
  AccountSummary,
  ConfidencePoint,
  CurrencyEquityPoint,
  DimensionRow,
  MfeMaePoint,
  MonthlyReturn,
  RiskAlert,
  RollingPoint,
  TradeRecord,
  YearReport,
} from "../types";
import { classifyResult } from "../trade-math";
import { sortTrades } from "./performance";

/** Per-calendar-month performance (closed trades, UTC). */
export function monthlyReturns(trades: TradeRecord[]): MonthlyReturn[] {
  const groups = new Map<string, TradeRecord[]>();
  for (const t of trades) {
    if (t.status !== "closed") continue;
    const month = t.exitTime.slice(0, 7); // YYYY-MM
    const arr = groups.get(month) ?? [];
    arr.push(t);
    groups.set(month, arr);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, group]) => {
      const wins = group.filter((t) => classifyResult(t.rMultiple) === "win");
      return {
        month,
        trades: group.length,
        netR: group.reduce((s, t) => s + t.rMultiple, 0),
        netPnl: group.reduce((s, t) => s + t.pnl, 0),
        winRate: group.length > 0 ? wins.length / group.length : 0,
      };
    });
}

/**
 * Rolling performance over a trailing window of trades. Reveals whether skill
 * is improving or decaying. One point per closed trade once the window fills.
 */
export function rollingPerformance(trades: TradeRecord[], window = 20): RollingPoint[] {
  const closed = sortTrades(trades.filter((t) => t.status === "closed"));
  if (closed.length < window) return [];
  const points: RollingPoint[] = [];
  for (let i = window - 1; i < closed.length; i++) {
    const slice = closed.slice(i - window + 1, i + 1);
    const wins = slice.filter((t) => classifyResult(t.rMultiple) === "win").length;
    const netR = slice.reduce((s, t) => s + t.rMultiple, 0);
    points.push({
      date: closed[i].exitTime,
      winRate: wins / window,
      expectancyR: netR / window,
      netR,
    });
  }
  return points;
}

/** MAE/MFE efficiency scatter — realized R vs the favourable/adverse extremes. */
export function mfeMaeScatter(trades: TradeRecord[]): MfeMaePoint[] {
  return trades
    .filter((t) => t.status === "closed" && t.mfe != null && t.mae != null)
    .map((t) => ({ mfe: t.mfe as number, mae: t.mae as number, rMultiple: t.rMultiple, label: t.symbol }));
}

/** Confidence (1-5) vs realized R scatter. */
export function confidenceScatter(trades: TradeRecord[]): ConfidencePoint[] {
  return trades
    .filter((t) => t.status === "closed" && t.confidence != null)
    .map((t) => ({ confidence: t.confidence as number, rMultiple: t.rMultiple, pnl: t.pnl }));
}

const DURATION_BUCKETS: { label: string; max: number }[] = [
  { label: "< 15m", max: 15 * 60 },
  { label: "15m–1h", max: 60 * 60 },
  { label: "1–4h", max: 4 * 60 * 60 },
  { label: "4–12h", max: 12 * 60 * 60 },
  { label: "12–24h", max: 24 * 60 * 60 },
  { label: "> 24h", max: Infinity },
];

/** Holding-time buckets with performance per bucket. */
export function durationBuckets(trades: TradeRecord[]): DimensionRow[] {
  const closed = trades.filter((t) => t.status === "closed" && t.durationSec != null);
  return DURATION_BUCKETS.map((b, i) => {
    const min = i === 0 ? 0 : DURATION_BUCKETS[i - 1].max;
    const group = closed.filter((t) => (t.durationSec as number) > min && (t.durationSec as number) <= b.max);
    const wins = group.filter((t) => classifyResult(t.rMultiple) === "win");
    const losses = group.filter((t) => classifyResult(t.rMultiple) === "loss");
    const grossWinR = wins.reduce((s, t) => s + t.rMultiple, 0);
    const grossLossR = Math.abs(losses.reduce((s, t) => s + t.rMultiple, 0));
    const netR = group.reduce((s, t) => s + t.rMultiple, 0);
    return {
      key: b.label,
      trades: group.length,
      wins: wins.length,
      losses: losses.length,
      winRate: group.length > 0 ? wins.length / group.length : 0,
      netR,
      netPnl: group.reduce((s, t) => s + t.pnl, 0),
      expectancy: group.length > 0 ? netR / group.length : 0,
      profitFactor: grossLossR > 0 ? grossWinR / grossLossR : grossWinR > 0 ? Infinity : 0,
    };
  }).filter((r) => r.trades > 0);
}

/**
 * Currency-denominated equity curve. Converts each trade's R-multiple into
 * account currency using `accountSize × riskPerTrade` as the per-trade risk,
 * then runs a running balance starting from `accountSize`. Returns [] when the
 * inputs are missing — the UI then shows an UNAVAILABLE state rather than
 * fabricating a currency curve.
 */
export function currencyEquity(
  trades: TradeRecord[],
  accountSize: number | null | undefined,
  riskPerTrade: number | null | undefined,
): CurrencyEquityPoint[] {
  if (!accountSize || accountSize <= 0) return [];
  const risk = (riskPerTrade && riskPerTrade > 0 ? riskPerTrade : 0.01) * accountSize;
  const closed = sortTrades(trades.filter((t) => t.status === "closed"));
  let equity = accountSize;
  let peak = accountSize;
  const points: CurrencyEquityPoint[] = [];
  for (const t of closed) {
    equity += t.rMultiple * risk;
    if (equity > peak) peak = equity;
    points.push({ date: t.exitTime, equity, drawdown: peak - equity });
  }
  return points;
}

/** Per-account P&L summaries. Accounts with no matching trades still appear. */
export function accountSummaries(
  trades: TradeRecord[],
  accounts: { id: string; name: string; broker?: string | null; currency: string; initialBalance: number }[],
): AccountSummary[] {
  return accounts.map((a) => {
    const group = trades.filter((t) => t.accountId === a.id && t.status === "closed");
    const netPnl = group.reduce((s, t) => s + t.pnl, 0);
    const netR = group.reduce((s, t) => s + t.rMultiple, 0);
    return {
      id: a.id,
      name: a.name,
      broker: a.broker ?? null,
      currency: a.currency,
      initialBalance: a.initialBalance,
      trades: group.length,
      netPnl,
      netR,
      equity: a.initialBalance + netPnl,
    };
  });
}

/**
 * Deterministic risk / behaviour alerts. No LLM. Thresholds are conservative
 * defaults; a future settings surface can expose them.
 */
export function riskAlerts(
  trades: TradeRecord[],
  options: { accountSize?: number | null; riskPerTrade?: number | null; maxTradesPerDay?: number } = {},
): RiskAlert[] {
  const alerts: RiskAlert[] = [];
  const closed = sortTrades(trades.filter((t) => t.status === "closed"));
  const open = trades.filter((t) => t.status === "open");

  // Losing streak.
  let streak = 0;
  for (const t of closed) {
    if (classifyResult(t.rMultiple) === "loss") streak++;
    else streak = 0;
  }
  if (streak >= 3) {
    alerts.push({
      level: streak >= 5 ? "danger" : "warn",
      title: `${streak} consecutive losses`,
      detail: "Consider halving size or stepping away until the streak breaks.",
    });
  }

  // Daily loss breach (in R).
  const byDay = new Map<string, number>();
  for (const t of closed) {
    const d = t.exitTime.slice(0, 10);
    byDay.set(d, (byDay.get(d) ?? 0) + t.rMultiple);
  }
  const worstDay = [...byDay.entries()].sort((a, b) => a[1] - b[1])[0];
  if (worstDay && worstDay[1] <= -3) {
    alerts.push({
      level: worstDay[1] <= -5 ? "danger" : "warn",
      title: `Worst day ${worstDay[1].toFixed(1)}R (${worstDay[0]})`,
      detail: "A daily stop-loss would have capped this drawdown.",
    });
  }

  // Overtrading.
  const maxPerDay = options.maxTradesPerDay ?? 5;
  const busiest = [...byDay.keys()].reduce<{ day: string; count: number }>((best, d) => {
    const count = closed.filter((t) => t.exitTime.slice(0, 10) === d).length;
    return count > best.count ? { day: d, count } : best;
  }, { day: "", count: 0 });
  if (busiest.count > maxPerDay) {
    alerts.push({
      level: "info",
      title: `${busiest.count} trades on ${busiest.day}`,
      detail: `Above your ${maxPerDay}/day baseline — check for overtrading.`,
    });
  }

  // Risk-rule violations.
  if (options.accountSize && options.accountSize > 0) {
    const maxRisk = options.accountSize * (options.riskPerTrade && options.riskPerTrade > 0 ? options.riskPerTrade : 0.01);
    const violations = closed.filter((t) => t.riskAmount != null && t.riskAmount > maxRisk).length;
    if (violations > 0) {
      alerts.push({
        level: violations >= 5 ? "warn" : "info",
        title: `${violations} risk-rule violation${violations > 1 ? "s" : ""}`,
        detail: `Trades risking more than ${(maxRisk).toLocaleString()} (account size × risk %).`,
      });
    }
  }

  // Open exposure reminder.
  if (open.length > 0) {
    alerts.push({
      level: "info",
      title: `${open.length} open position${open.length > 1 ? "s" : ""}`,
      detail: "Unrealized P&L is not tracked — close them to include in analytics.",
    });
  }

  return alerts;
}

/** Realized P&L and costs by calendar year (tax/reporting). */
export function yearReports(trades: TradeRecord[]): YearReport[] {
  const groups = new Map<string, TradeRecord[]>();
  for (const t of trades) {
    if (t.status !== "closed") continue;
    const year = t.exitTime.slice(0, 4);
    const arr = groups.get(year) ?? [];
    arr.push(t);
    groups.set(year, arr);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([year, group]) => ({
      year,
      trades: group.length,
      wins: group.filter((t) => classifyResult(t.rMultiple) === "win").length,
      losses: group.filter((t) => classifyResult(t.rMultiple) === "loss").length,
      netPnl: group.reduce((s, t) => s + t.pnl, 0),
      netR: group.reduce((s, t) => s + t.rMultiple, 0),
      fees: group.reduce((s, t) => s + t.commission + t.fee, 0),
    }));
}
