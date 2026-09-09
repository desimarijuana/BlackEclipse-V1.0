// ── Dimensional analytics — break performance down by any dimension ──────────
// Extensible: add a new dimension by providing a key extractor. Each dimension
// returns a sorted DimensionRow[] (best → worst by net R).

import type { DimensionRow, TradeRecord } from "../types";
import { classifyResult } from "../trade-math";

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
    const wins = group.filter((t) => classifyResult(t.rMultiple) === "win");
    const losses = group.filter((t) => classifyResult(t.rMultiple) === "loss");
    const netR = group.reduce((s, t) => s + t.rMultiple, 0);
    const netPnl = group.reduce((s, t) => s + t.pnl, 0);
    const grossWinR = wins.reduce((s, t) => s + t.rMultiple, 0);
    const grossLossR = Math.abs(losses.reduce((s, t) => s + t.rMultiple, 0));
    rows.push({
      key,
      trades: group.length,
      wins: wins.length,
      losses: losses.length,
      winRate: group.length > 0 ? wins.length / group.length : 0,
      netR,
      netPnl,
      expectancy: group.length > 0 ? netR / group.length : 0,
      profitFactor: grossLossR > 0 ? grossWinR / grossLossR : grossWinR > 0 ? Infinity : 0,
    });
  }

  return rows.sort((a, b) => b.netR - a.netR);
}

export const bySymbol = (trades: TradeRecord[]) => breakdown(trades, (t) => t.symbol);
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

/** Trading hour (UTC, 0-23) — reveals the trader's best time of day. */
export const byHour = (trades: TradeRecord[]) =>
  breakdown(trades, (t) => {
    const d = new Date(t.exitTime);
    const h = d.getUTCHours();
    return `${String(h).padStart(2, "0")}:00`;
  });
