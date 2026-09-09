// ── Psychology analytics — correlate emotional state with outcomes ───────────
// Deterministic: groups closed trades by recorded emotion and reports the
// average R / win rate for each state.

import type { DimensionRow, TradeRecord } from "../types";
import { byEmotion } from "./dimensions";

export const EMOTIONS = [
  "Calm",
  "Focused",
  "Confident",
  "Fearful",
  "FOMO",
  "Revenge",
  "Bored",
  "Overconfident",
  "Hesitant",
] as const;

export type Emotion = (typeof EMOTIONS)[number];

/** Performance by emotional state, best → worst. */
export function psychologyBreakdown(trades: TradeRecord[]): DimensionRow[] {
  return byEmotion(trades);
}

/** The single most costly emotional leak (most negative net R). */
export function biggestLeak(trades: TradeRecord[]): DimensionRow | null {
  const rows = psychologyBreakdown(trades);
  const negative = rows.filter((r) => r.netR < 0);
  if (negative.length === 0) return null;
  return negative[negative.length - 1]; // sorted best→worst, so last is worst
}

/** The emotional state with the best average R. */
export function bestEmotion(trades: TradeRecord[]): DimensionRow | null {
  const rows = psychologyBreakdown(trades);
  return rows.length > 0 ? rows[0] : null;
}

/** Confidence level breakdown (1-5) — reveals whether higher confidence wins. */
export function byConfidence(trades: TradeRecord[]): DimensionRow[] {
  const closed = trades.filter((t) => t.status === "closed" && t.confidence != null);
  return byEmotion(closed.map((t) => ({ ...t, emotion: `Confidence ${t.confidence}` })));
}

/** Correlation between confidence level and outcome (Pearson on R-multiple). */
export function confidenceCorrelation(trades: TradeRecord[]): number | null {
  const pts = trades
    .filter((t) => t.status === "closed" && t.confidence != null)
    .map((t) => ({ x: t.confidence as number, y: t.rMultiple }));
  if (pts.length < 3) return null;
  const n = pts.length;
  const sumX = pts.reduce((s, p) => s + p.x, 0);
  const sumY = pts.reduce((s, p) => s + p.y, 0);
  const sumXy = pts.reduce((s, p) => s + p.x * p.y, 0);
  const sumX2 = pts.reduce((s, p) => s + p.x * p.x, 0);
  const sumY2 = pts.reduce((s, p) => s + p.y * p.y, 0);
  const denom = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  if (denom === 0) return null;
  return (n * sumXy - sumX * sumY) / denom;
}

/** Biggest behavioral leak by net R (negative emotion or mistake). */
export function biggestLeakByMistake(trades: TradeRecord[]): string | null {
  const mistakes = new Map<string, number>();
  for (const t of trades) {
    if (t.status !== "closed" || !t.mistakes) continue;
    try {
      const arr = JSON.parse(t.mistakes) as string[];
      for (const m of arr) mistakes.set(m, (mistakes.get(m) ?? 0) + t.rMultiple);
    } catch { /* ignore */ }
  }
  let worst: string | null = null;
  let worstR = 0;
  for (const [m, r] of mistakes) {
    if (r < worstR) { worstR = r; worst = m; }
  }
  return worst;
}
