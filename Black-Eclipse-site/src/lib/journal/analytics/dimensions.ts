// ── Dimensional analytics — break performance down by any dimension ──────────
// Extensible: add a new dimension by providing a key extractor. Each dimension
// returns a sorted DimensionRow[] (best → worst by net R).

import type { DimensionRow, TradeRecord } from "../types";
import { classifyTradeOutcome } from "../trade-math";

type KeyExtractor = (t: TradeRecord) => string | null | undefined;

function breakdown(trades: TradeRecord[], extract: KeyExtractor): DimensionRow[] {
  const groups = new Map<string, TradeRecord[]>();
  for (const t of trades) {
    if (t.status !== "closed") continue;
    const key = extract(t);
    if (!key) continue;
    const arr = groups.get(key) ?? [];
    arr.push(t);
    groups.set(key, arr);
  }

  const rows: DimensionRow[] = [];
  for (const [key, group] of groups) {
    const wins = group.filter((t) => classifyTradeOutcome(t) === "win");
    const losses = group.filter((t) => classifyTradeOutcome(t) === "loss");
    const netR = group.reduce((s, t) => s + t.rMultiple, 0);
    const netPnl = group.reduce((s, t) => s + t.pnl, 0);
    const grossWinPnl = wins.reduce((s, t) => s + Math.max(0, t.pnl), 0);
    const grossLossPnl = Math.abs(losses.reduce((s, t) => s + Math.min(0, t.pnl), 0));
    rows.push({
      key,
      trades: group.length,
      wins: wins.length,
      losses: losses.length,
      winRate: group.length > 0 ? wins.length / group.length : 0,
      netR,
      netPnl,
      expectancy: group.length > 0 ? netR / group.length : 0,
      profitFactor: grossLossPnl > 0 ? grossWinPnl / grossLossPnl : grossWinPnl > 0 ? Infinity : 0,
    });
  }

  // When no trade carries an R basis every netR is 0; fall back to P&L so the
  // "best/worst" ordering is still meaningful instead of arbitrary.
  const anyR = rows.some((row) => row.netR !== 0);
  return rows.sort((a, b) => (anyR ? b.netR - a.netR : b.netPnl - a.netPnl));
}

export const bySymbol = (trades: TradeRecord[]) => breakdown(trades, (t) => t.symbol);
export const byStrategy = (trades: TradeRecord[]) => breakdown(trades, (t) => t.strategyName ?? t.strategyId ?? null);
export const bySetup = (trades: TradeRecord[]) => breakdown(trades, (t) => t.setupName ?? t.setupId ?? null);
export const bySession = (trades: TradeRecord[]) => breakdown(trades, (t) => t.session ?? null);
export const byDirection = (trades: TradeRecord[]) => breakdown(trades, (t) => t.direction);
export const byDayOfWeek = (trades: TradeRecord[]) =>
  breakdown(trades, (t) => {
    const d = new Date(t.exitTime);
    return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][d.getUTCDay()];
  });
export const byEmotion = (trades: TradeRecord[]) => breakdown(trades, (t) => t.emotion ?? null);
export const byTimeframe = (trades: TradeRecord[]) => breakdown(trades, (t) => t.timeframe ?? null);
export const byRegime = (trades: TradeRecord[]) => breakdown(trades, (t) => t.marketRegime ?? null);
export const byTrend = (trades: TradeRecord[]) => breakdown(trades, (t) => t.trend ?? null);
/** Per trading account (unassigned trades are grouped, not dropped). */
export const byAccount = (trades: TradeRecord[]) =>
  breakdown(trades, (t) => t.accountName ?? "Unassigned");
/** Per broker magic number. Manual/CSV trades have no magic and are skipped. */
export const byMagic = (trades: TradeRecord[]) =>
  breakdown(trades, (t) => (t.magic != null && t.magic !== 0 ? String(t.magic) : null));

/** Trading hour (UTC, 0-23) — reveals the trader's best time of day. */
export const byHour = (trades: TradeRecord[]) =>
  breakdown(trades, (t) => {
    const d = new Date(t.exitTime);
    const h = d.getUTCHours();
    return `${String(h).padStart(2, "0")}:00`;
  });
