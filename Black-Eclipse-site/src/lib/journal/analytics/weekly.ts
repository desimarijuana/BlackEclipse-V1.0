// ── Weekly Review — deterministic performance summary + interpretation ───────
// Generates a structured weekly review from the analytics engine. All facts
// are computed, never fabricated. A future AI layer can interpret these
// structured facts, but the numbers here are always real.

import type { DimensionRow, TradeRecord } from "../types";
import { computePerformance } from "./performance";
import { computeDiscipline } from "./discipline";
import { bySymbol, bySetup, bySession, byDayOfWeek, byHour } from "./dimensions";
import { biggestLeak } from "./psychology";
import { fmtR } from "../format";

export interface ReviewSection {
  title: string;
  items: { label: string; value: string; tone?: "pos" | "neg" | "neutral" }[];
}

export interface WeeklyReview {
  periodStart: string; // YYYY-MM-DD
  periodEnd: string;
  performance: {
    trades: number;
    winRate: number;
    netR: number;
    netPnl: number;
    profitFactor: number;
  };
  whatWorked: DimensionRow[];
  whatHurt: DimensionRow[];
  biggestLeak: DimensionRow | null;
  bestDay: string | null;
  discipline: number;
  sections: ReviewSection[];
}

/** Filter trades to a date range (inclusive) by exit time. */
export function filterByRange(trades: TradeRecord[], start: string, end: string): TradeRecord[] {
  const s = new Date(start + "T00:00:00Z").getTime();
  const e = new Date(end + "T23:59:59.999Z").getTime();
  return trades.filter((t) => {
    const ts = Date.parse(t.exitTime);
    return ts >= s && ts <= e;
  });
}

/** Build a weekly review for a 7-day range. */
export function buildWeeklyReview(trades: TradeRecord[], start: string, end: string): WeeklyReview {
  const range = filterByRange(trades, start, end);
  const perf = computePerformance(range);
  const symbols = bySymbol(range);
  const setups = bySetup(range);
  const sessions = bySession(range);
  const days = byDayOfWeek(range);
  const hours = byHour(range);
  const leak = biggestLeak(range);

  const whatWorked: DimensionRow[] = [];
  const whatHurt: DimensionRow[] = [];
  for (const r of [...symbols, ...setups, ...sessions]) {
    if (r.netR > 0.5) whatWorked.push(r);
    else if (r.netR < -0.5) whatHurt.push(r);
  }
  // Dedupe by key, keeping the biggest magnitude.
  const dedupe = (rows: DimensionRow[]) => {
    const byKey = new Map<string, DimensionRow>();
    for (const r of rows) {
      const existing = byKey.get(r.key);
      if (!existing || Math.abs(r.netR) > Math.abs(existing.netR)) byKey.set(r.key, r);
    }
    return [...byKey.values()].sort((a, b) => b.netR - a.netR).slice(0, 4);
  };

  const bestDay = hours.length > 0 ? hours[0].key : null;

  const sections: ReviewSection[] = [];
  sections.push({
    title: "What Worked",
    items: dedupe(whatWorked).map((r) => ({
      label: r.key,
      value: fmtR(r.netR),
      tone: r.netR >= 0 ? "pos" : "neg",
    })),
  });
  sections.push({
    title: "What Hurt",
    items: dedupe(whatHurt).map((r) => ({
      label: r.key,
      value: fmtR(r.netR),
      tone: r.netR < 0 ? "neg" : "pos",
    })),
  });
  sections.push({
    title: "Sessions",
    items: sessions.slice(0, 3).map((r) => ({ label: r.key, value: fmtR(r.netR), tone: r.netR >= 0 ? "pos" : "neg" })),
  });
  sections.push({
    title: "Days of Week",
    items: days.slice(0, 3).map((r) => ({ label: r.key, value: fmtR(r.netR), tone: r.netR >= 0 ? "pos" : "neg" })),
  });

  return {
    periodStart: start,
    periodEnd: end,
    performance: {
      trades: perf.totalTrades,
      winRate: perf.winRate,
      netR: perf.netR,
      netPnl: perf.netPnl,
      profitFactor: perf.profitFactor,
    },
    whatWorked: dedupe(whatWorked),
    whatHurt: dedupe(whatHurt),
    biggestLeak: leak,
    bestDay,
    discipline: perf.totalTrades > 0 ? computeDiscipline(range).total : 0,
    sections,
  };
}

/** Generate reviews for the last N weeks ending today (Sunday). */
export function buildRecentWeeklyReviews(trades: TradeRecord[], weeks = 4): WeeklyReview[] {
  const out: WeeklyReview[] = [];
  const today = new Date();
  // Find the most recent Sunday (end of week).
  const endDow = today.getUTCDay();
  const end = new Date(today);
  end.setUTCDate(end.getUTCDate() + ((7 - endDow) % 7));
  end.setUTCHours(0, 0, 0, 0);

  for (let i = 0; i < weeks; i++) {
    const weekEnd = new Date(end);
    weekEnd.setUTCDate(end.getUTCDate() - i * 7);
    const weekStart = new Date(weekEnd);
    weekStart.setUTCDate(weekEnd.getUTCDate() - 6);
    const s = weekStart.toISOString().slice(0, 10);
    const e = weekEnd.toISOString().slice(0, 10);
    out.push(buildWeeklyReview(trades, s, e));
  }
  return out;
}
