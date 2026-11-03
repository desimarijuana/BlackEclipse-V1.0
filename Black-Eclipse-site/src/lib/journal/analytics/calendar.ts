// ── Calendar aggregation — per-day performance for the heatmap ───────────────
// Groups closed trades by day and computes the metrics shown on hover.

import type { DayAggregate, TradeRecord } from "../types";
import { classifyTradeOutcome, hasRBasis } from "../trade-math";

export function aggregateDays(trades: TradeRecord[]): DayAggregate[] {
  const byDay = new Map<string, TradeRecord[]>();
  for (const t of trades) {
    if (t.status !== "closed") continue;
    const day = t.exitTime.slice(0, 10);
    const arr = byDay.get(day) ?? [];
    arr.push(t);
    byDay.set(day, arr);
  }

  const days: DayAggregate[] = [];
  for (const [date, group] of byDay) {
    const wins = group.filter((t) => classifyTradeOutcome(t) === "win");
    const losses = group.filter((t) => classifyTradeOutcome(t) === "loss");
    const breakevens = group.filter((t) => classifyTradeOutcome(t) === "breakeven");
    const rAvailable = group.some(hasRBasis);
    const netR = group.reduce((s, t) => s + t.rMultiple, 0);
    const netPnl = group.reduce((s, t) => s + t.pnl, 0);
    const rValues = group.filter(hasRBasis).map((t) => t.rMultiple);
    days.push({
      date,
      trades: group.length,
      wins: wins.length,
      losses: losses.length,
      breakevens: breakevens.length,
      netPnl,
      netR,
      bestR: rValues.length > 0 ? Math.max(...rValues) : 0,
      worstR: rValues.length > 0 ? Math.min(...rValues) : 0,
      rAvailable,
      discipline: null, // filled by the discipline engine when available
    });
  }

  return days.sort((a, b) => a.date.localeCompare(b.date));
}

/** Build a contiguous day map (including empty days) for a date range. */
export function dayMapForRange(
  trades: TradeRecord[],
  start: string,
  end: string,
): Map<string, DayAggregate> {
  const map = new Map<string, DayAggregate>();
  const cursor = new Date(start + "T00:00:00Z");
  const endDate = new Date(end + "T00:00:00Z");
  while (cursor <= endDate) {
    const key = cursor.toISOString().slice(0, 10);
    map.set(key, {
      date: key,
      trades: 0,
      wins: 0,
      losses: 0,
      breakevens: 0,
      netPnl: 0,
      netR: 0,
      bestR: 0,
      worstR: 0,
      rAvailable: false,
      discipline: null,
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  for (const d of aggregateDays(trades)) {
    if (map.has(d.date)) map.set(d.date, d);
  }
  return map;
}
