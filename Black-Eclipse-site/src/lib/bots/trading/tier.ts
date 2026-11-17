// ── Tier recommendation ─────────────────────────────────────────────────────
// The ladder is the safety spine: L0 proposes, L1 fills demo, L2 fills live.
// This module answers "what has this bot EARNED?" and "what is still missing?".
//
// It never grants anything. It returns a recommendation the operator accepts with
// one click, so live authority stays a human decision (the server enforces it).
//
// Thresholds are deliberately conservative and visible: a bot that has not seen
// real shadow decisions does not get to touch money, and a demo record needs both
// sample size and a positive edge before live is even suggested.

import type { TradingMode, TradingTier } from "./types";

export interface TrackRecord {
  mode: TradingMode;
  /** Decisions made in shadow/demo where a signal existed (not no-signal bars). */
  shadowDecisions: number;
  /** Closed trades attributed to this bot. */
  closedTrades?: number;
  wins?: number;
  losses?: number;
  /** Days since the bot first ran. */
  daysActive?: number;
  /** Strategy gates, mirrored from the quant store. */
  hasBacktest?: boolean;
  approved?: boolean;
}

export interface TierRequirements {
  shadowDecisions: number;
  closedTrades: number;
  winRate: number;
  profitFactor: number;
  daysActive: number;
}

/** What L1 needs: enough shadow evidence that the wiring works. */
export const L1_REQUIREMENTS: TierRequirements = {
  shadowDecisions: 20,
  closedTrades: 0,
  winRate: 0,
  profitFactor: 0,
  daysActive: 0,
};

/** What L2 needs: a real demo record with a positive, non-trivial edge. */
export const L2_REQUIREMENTS: TierRequirements = {
  shadowDecisions: 50,
  closedTrades: 30,
  winRate: 0.45,
  profitFactor: 1.2,
  daysActive: 14,
};

export interface TierRecommendation {
  /** The tier the bot has earned today. */
  tier: TradingTier;
  /** The next mode worth trying, or the current one. */
  next: TradingMode;
  eligibleForLive: boolean;
  reasons: string[];
  blockers: string[];
}

export function minimumTierFor(mode: TradingMode): TradingTier {
  if (mode === "live") return "l2";
  if (mode === "demo") return "l1";
  return "l0";
}

export function tierAllows(mode: TradingMode, tier: TradingTier): boolean {
  const order: Record<TradingTier, number> = { l0: 0, l1: 1, l2: 2 };
  return order[tier] >= order[minimumTierFor(mode)];
}

export function winRate(record: TrackRecord): number {
  const wins = Math.max(0, record.wins ?? 0);
  const losses = Math.max(0, record.losses ?? 0);
  const total = wins + losses;
  return total ? wins / total : 0;
}

/** Gross-profit / gross-loss approximation from wins/losses (no invented money). */
export function profitFactor(record: TrackRecord): number {
  const wins = Math.max(0, record.wins ?? 0);
  const losses = Math.max(0, record.losses ?? 0);
  if (!losses) return wins > 0 ? Number.POSITIVE_INFINITY : 0;
  return wins / losses;
}

function check(record: TrackRecord, req: TierRequirements): string[] {
  const missing: string[] = [];
  if (record.shadowDecisions < req.shadowDecisions) {
    missing.push(
      `${req.shadowDecisions - record.shadowDecisions} more shadow decision${
        req.shadowDecisions - record.shadowDecisions === 1 ? "" : "s"
      } (need ${req.shadowDecisions})`,
    );
  }
  if (req.closedTrades > 0 && (record.closedTrades ?? 0) < req.closedTrades) {
    missing.push(
      `${req.closedTrades - (record.closedTrades ?? 0)} more closed demo trade${
        req.closedTrades - (record.closedTrades ?? 0) === 1 ? "" : "s"
      } (need ${req.closedTrades})`,
    );
  }
  if (req.winRate > 0 && winRate(record) < req.winRate) {
    missing.push(`a demo win rate of ${(req.winRate * 100).toFixed(0)}%`);
  }
  if (req.profitFactor > 0 && profitFactor(record) < req.profitFactor) {
    missing.push(`a profit factor of ${req.profitFactor.toFixed(1)}`);
  }
  if (req.daysActive > 0 && (record.daysActive ?? 0) < req.daysActive) {
    missing.push(`${req.daysActive} days of track record`);
  }
  if (record.hasBacktest === false) missing.push("a completed backtest");
  if (record.approved === false) missing.push("an approved strategy version");
  return missing;
}

/**
 * The recommendation. Live is suggested only when the demo record clears every
 * gate; otherwise the bot stays at the tier it has earned and says why.
 */
export function recommendTier(record: TrackRecord): TierRecommendation {
  const reasons: string[] = [];
  if (record.mode === "shadow" && record.shadowDecisions > 0) {
    reasons.push(
      `${record.shadowDecisions} shadow decision${record.shadowDecisions === 1 ? "" : "s"} recorded.`,
    );
  }

  const l1Blockers = check(record, L1_REQUIREMENTS);
  if (record.mode === "shadow") {
    return l1Blockers.length
      ? {
          tier: "l0",
          next: "shadow",
          eligibleForLive: false,
          reasons,
          blockers: l1Blockers,
        }
      : {
          tier: "l1",
          next: "demo",
          eligibleForLive: false,
          reasons: [...reasons, "Shadow evidence is enough to fill a demo account."],
          blockers: [],
        };
  }

  const l2Blockers = check(record, L2_REQUIREMENTS);
  if (l2Blockers.length) {
    return {
      // L2 is EARNED, never assumed from the mode a bot happens to be in.
      tier: "l1",
      next: "demo",
      eligibleForLive: false,
      reasons,
      blockers: l2Blockers,
    };
  }
  return {
    tier: "l2",
    next: "live",
    eligibleForLive: true,
    reasons: [
      ...reasons,
      `Demo record clears the live gate (${(winRate(record) * 100).toFixed(0)}% win rate).`,
    ],
    blockers: [],
  };
}

export interface L2Eligibility {
  eligible: boolean;
  blockers: string[];
  warnings: string[];
}

/**
 * Can the operator be OFFERED the L2 request? Only the gates this surface can
 * actually measure are blockers (shadow evidence, days, strategy review). Trade
 * P&L lives in the journal and is named as a warning, not faked into a score.
 */
export function l2Eligibility(input: {
  shadowDecisions: number;
  daysActive: number;
  hasBacktest?: boolean;
  approved?: boolean;
}): L2Eligibility {
  const blockers: string[] = [];
  if (input.shadowDecisions < L2_REQUIREMENTS.shadowDecisions) {
    blockers.push(
      `${L2_REQUIREMENTS.shadowDecisions - input.shadowDecisions} more decisions (need ${L2_REQUIREMENTS.shadowDecisions})`,
    );
  }
  if (input.daysActive < L2_REQUIREMENTS.daysActive) {
    blockers.push(`${L2_REQUIREMENTS.daysActive} days of track record`);
  }
  if (input.hasBacktest === false) blockers.push("a completed backtest");
  if (input.approved === false) blockers.push("an approved strategy version");
  const warnings = [
    "Closed-trade P&L and win rate live in the journal; review them before going live.",
    "L2 is an operator decision: live orders still need an armed connection and a bot-pinned mandate.",
  ];
  return { eligible: blockers.length === 0, blockers, warnings };
}

/** "L1 — 20 shadow decisions" for a compact UI label. */
export function describeRecommendation(recommendation: TierRecommendation): string {  if (recommendation.eligibleForLive) {
    return "L2 — eligible for live execution. Raising it is your decision.";
  }
  if (recommendation.blockers.length) {
    return `${recommendation.tier.toUpperCase()} — needs ${recommendation.blockers
      .slice(0, 2)
      .join(", ")}.`;
  }
  return `${recommendation.tier.toUpperCase()} — ready to raise to ${recommendation.next}.`;
}
