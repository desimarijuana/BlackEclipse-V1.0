import { describe, expect, it } from "vitest";
import {
  L1_REQUIREMENTS,
  L2_REQUIREMENTS,
  describeRecommendation,
  l2Eligibility,
  minimumTierFor,
  profitFactor,
  recommendTier,
  tierAllows,
  winRate,
} from "./tier";
import type { TrackRecord } from "./tier";

function record(patch: Partial<TrackRecord> = {}): TrackRecord {
  return {
    mode: "shadow",
    shadowDecisions: 0,
    closedTrades: 0,
    wins: 0,
    losses: 0,
    daysActive: 0,
    hasBacktest: true,
    approved: true,
    ...patch,
  };
}

describe("the ladder", () => {
  it("maps a mode to its minimum tier", () => {
    expect(minimumTierFor("shadow")).toBe("l0");
    expect(minimumTierFor("demo")).toBe("l1");
    expect(minimumTierFor("live")).toBe("l2");
  });

  it("never lets a lower tier act in a higher mode", () => {
    expect(tierAllows("demo", "l0")).toBe(false);
    expect(tierAllows("demo", "l1")).toBe(true);
    expect(tierAllows("live", "l1")).toBe(false);
    expect(tierAllows("live", "l2")).toBe(true);
    expect(tierAllows("shadow", "l0")).toBe(true);
  });
});

describe("recommendations", () => {
  it("keeps a fresh shadow bot at L0 and says what is missing", () => {
    const rec = recommendTier(record({ shadowDecisions: 4 }));
    expect(rec.tier).toBe("l0");
    expect(rec.next).toBe("shadow");
    expect(rec.eligibleForLive).toBe(false);
    expect(rec.blockers.join(" ")).toContain("16 more shadow decisions");
    expect(describeRecommendation(rec)).toContain("needs");
  });

  it("suggests demo once shadow evidence clears L1", () => {
    const rec = recommendTier(record({ shadowDecisions: L1_REQUIREMENTS.shadowDecisions }));
    expect(rec.tier).toBe("l1");
    expect(rec.next).toBe("demo");
    expect(rec.blockers).toEqual([]);
  });

  it("blocks L1 when the strategy has no backtest", () => {
    const rec = recommendTier(
      record({ shadowDecisions: 60, hasBacktest: false }),
    );
    expect(rec.tier).toBe("l0");
    expect(rec.blockers.join(" ")).toMatch(/backtest/);
  });

  it("requires a real demo record before live", () => {
    const rec = recommendTier(
      record({
        mode: "demo",
        shadowDecisions: 20,
        closedTrades: 12,
        wins: 9,
        losses: 3,
        daysActive: 5,
      }),
    );
    expect(rec.tier).toBe("l1");
    expect(rec.eligibleForLive).toBe(false);
    expect(rec.blockers.join(" ")).toContain("18 more closed demo trades");
  });

  it("blocks live on a losing demo record", () => {
    const rec = recommendTier(
      record({
        mode: "demo",
        shadowDecisions: L2_REQUIREMENTS.shadowDecisions,
        closedTrades: 40,
        wins: 10,
        losses: 30,
        daysActive: 30,
      }),
    );
    expect(rec.eligibleForLive).toBe(false);
    expect(rec.blockers.join(" ")).toMatch(/win rate/);
  });

  it("grants the recommendation (not the tier) once every gate clears", () => {
    const rec = recommendTier(
      record({
        mode: "demo",
        shadowDecisions: L2_REQUIREMENTS.shadowDecisions,
        closedTrades: 30,
        wins: 20,
        losses: 10,
        daysActive: 30,
      }),
    );
    expect(rec.tier).toBe("l2");
    expect(rec.next).toBe("live");
    expect(rec.eligibleForLive).toBe(true);
    expect(rec.reasons.join(" ")).toMatch(/win rate/);
    expect(describeRecommendation(rec)).toContain("your decision");
  });

  it("computes win rate and profit factor without inventing trades", () => {
    expect(winRate(record({ wins: 1, losses: 3 }))).toBe(0.25);
    expect(winRate(record())).toBe(0);
    expect(profitFactor(record({ wins: 3, losses: 0 }))).toBe(
      Number.POSITIVE_INFINITY,
    );
    expect(profitFactor(record({ wins: 0, losses: 0 }))).toBe(0);
    expect(profitFactor(record({ wins: 3, losses: 2 }))).toBe(1.5);
  });
});

describe("L2 eligibility for the ladder", () => {
  it("offers the request only after enough decisions and days", () => {
    const early = l2Eligibility({ shadowDecisions: 10, daysActive: 3 });
    expect(early.eligible).toBe(false);
    expect(early.blockers.join(" ")).toMatch(/40 more decisions/);
    expect(early.blockers.join(" ")).toMatch(/14 days/);

    const ready = l2Eligibility({ shadowDecisions: 50, daysActive: 14 });
    expect(ready.eligible).toBe(true);
    expect(ready.blockers).toEqual([]);
    expect(ready.warnings.join(" ")).toMatch(/journal/i);
    expect(ready.warnings.join(" ")).toMatch(/armed connection/i);
  });

  it("blocks when the strategy has no backtest or approval", () => {
    const result = l2Eligibility({
      shadowDecisions: 80,
      daysActive: 30,
      hasBacktest: false,
      approved: false,
    });
    expect(result.eligible).toBe(false);
    expect(result.blockers).toContain("a completed backtest");
    expect(result.blockers).toContain("an approved strategy version");
  });
});
