// ── Trade Similarity — find historically similar trades ──────────────────────
// Uses structured features (symbol, direction, strategy, setup, session,
// timeframe, regime, trend, risk, R:R) rather than embeddings. Returns the
// most similar closed trades plus their aggregate performance.

import type { TradeRecord } from "../types";
import { classifyTradeOutcome } from "../trade-math";

export interface SimilarTrade {
  trade: TradeRecord;
  score: number; // 0..1 similarity
}

export interface SimilarityResult {
  similar: SimilarTrade[];
  winRate: number;
  averageR: number;
  medianR: number;
  count: number;
}

/** Feature weights — tune which dimensions matter most. */
const WEIGHTS: Record<string, number> = {
  symbol: 0.25,
  direction: 0.1,
  strategy: 0.15,
  setup: 0.15,
  session: 0.1,
  timeframe: 0.1,
  regime: 0.05,
  trend: 0.05,
  risk: 0.03,
  rr: 0.02,
};

function eq(a: string | null | undefined, b: string | null | undefined): number {
  if (!a || !b) return 0;
  return a.toLowerCase() === b.toLowerCase() ? 1 : 0;
}

/** Similarity score between a target and a candidate trade (0..1). */
export function similarityScore(target: TradeRecord, candidate: TradeRecord): number {
  let score = 0;
  score += eq(target.symbol, candidate.symbol) * WEIGHTS.symbol;
  score += eq(target.direction, candidate.direction) * WEIGHTS.direction;
  score += eq(target.strategyName ?? target.strategyId, candidate.strategyName ?? candidate.strategyId) * WEIGHTS.strategy;
  score += eq(target.setupName ?? target.setupId, candidate.setupName ?? candidate.setupId) * WEIGHTS.setup;
  score += eq(target.session, candidate.session) * WEIGHTS.session;
  score += eq(target.timeframe, candidate.timeframe) * WEIGHTS.timeframe;
  score += eq(target.marketRegime, candidate.marketRegime) * WEIGHTS.regime;
  score += eq(target.trend, candidate.trend) * WEIGHTS.trend;

  // Risk similarity (normalized difference).
  if (target.riskAmount && candidate.riskAmount) {
    const diff = Math.abs(target.riskAmount - candidate.riskAmount) / Math.max(target.riskAmount, candidate.riskAmount, 1);
    score += (1 - Math.min(1, diff)) * WEIGHTS.risk;
  }
  // R:R similarity.
  if (target.actualRR != null && candidate.actualRR != null) {
    const diff = Math.abs(target.actualRR - candidate.actualRR) / Math.max(target.actualRR, candidate.actualRR, 0.1);
    score += (1 - Math.min(1, diff)) * WEIGHTS.rr;
  }

  return Math.max(0, Math.min(1, score));
}

/**
 * Find the most similar closed trades to a target.
 *
 * @param target the trade to match against
 * @param trades all trades (the target itself is excluded)
 * @param limit max number of similar trades to return
 * @param minScore minimum similarity to include
 */
export function findSimilarTrades(
  target: TradeRecord,
  trades: TradeRecord[],
  limit = 10,
  minScore = 0.2,
): SimilarityResult {
  const candidates = trades.filter(
    (t) => t.id !== target.id && t.status === "closed",
  );

  const scored = candidates
    .map((t) => ({ trade: t, score: similarityScore(target, t) }))
    .filter((s) => s.score >= minScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  const rValues = scored.map((s) => s.trade.rMultiple);
  const wins = scored.filter((s) => classifyTradeOutcome(s.trade) === "win").length;
  const sortedR = [...rValues].sort((a, b) => a - b);
  const medianR = sortedR.length > 0
    ? sortedR.length % 2 === 1
      ? sortedR[Math.floor(sortedR.length / 2)]
      : (sortedR[sortedR.length / 2 - 1] + sortedR[sortedR.length / 2]) / 2
    : 0;

  return {
    similar: scored,
    winRate: scored.length > 0 ? wins / scored.length : 0,
    averageR: rValues.length > 0 ? rValues.reduce((s, v) => s + v, 0) / rValues.length : 0,
    medianR,
    count: scored.length,
  };
}
