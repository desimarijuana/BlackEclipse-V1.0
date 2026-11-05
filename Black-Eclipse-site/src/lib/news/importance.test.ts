import { describe, it, expect } from "vitest";
import {
  scoreNewsImportance,
  rankNewsImportance,
  type ImportanceNewsInput,
} from "./importance";

const NOW = Date.parse("2026-11-04T15:00:00Z");

function item(overrides: Partial<ImportanceNewsInput> = {}): ImportanceNewsInput {
  return {
    headline: "Fed holds rates steady",
    summary: "",
    tier: 1,
    category: "CENTRAL BANKS",
    region: "US",
    ticker: "SPY",
    sentiment: "neutral",
    timestamp: new Date(NOW - 5 * 60_000).toISOString(),
    sourceCount: 4,
    ...overrides,
  };
}

describe("scoreNewsImportance", () => {
  it("flags a fresh, corroborated Tier-1 macro story as critical", () => {
    const r = scoreNewsImportance(item(), { now: NOW, portfolio: ["SPY"] });
    expect(r.level).toBe("critical");
    expect(r.score).toBeGreaterThanOrEqual(75);
    expect(r.isBreaking).toBe(true);
    expect(r.confidence).toBe("high");
    expect(r.horizon).toBe("macro");
    expect(r.reasons).toContain("Tier-1 wire");
    expect(r.reasons).toContain("4 sources");
    expect(r.reasons.some((x) => x.includes("affects your holding"))).toBe(true);
    expect(r.affected).toContain("SPY");
  });

  it("keeps an old, single-source, low-tier analysis piece low", () => {
    const r = scoreNewsImportance(
      item({
        headline: "Why 3 stocks could rally next year",
        tier: 4,
        category: "TECH",
        ticker: null,
        sourceCount: 1,
        sentiment: "bullish",
        timestamp: new Date(NOW - 3 * 24 * 60 * 60_000).toISOString(),
      }),
      { now: NOW },
    );
    expect(r.level).toBe("low");
    expect(r.score).toBeLessThan(38);
    expect(r.isBreaking).toBe(false);
    expect(r.confidence).toBe("low");
    expect(r.reasons).toContain("analysis, not a new event");
    expect(r.reasons).toContain("stale");
  });

  it("boosts a watchlist ticker over an unrelated one", () => {
    const base = item({
      headline: "Nvidia unveils new chip",
      category: "TECH",
      sourceCount: 1,
      tier: 3,
      timestamp: new Date(NOW - 40 * 60_000).toISOString(),
    });
    const plain = scoreNewsImportance(base, { now: NOW });
    const watched = scoreNewsImportance(base, { now: NOW, watchlist: ["NVDA"] });
    expect(watched.score).toBeGreaterThan(plain.score);
    expect(watched.reasons.some((r) => r.includes("watchlist"))).toBe(true);
  });

  it("is deterministic for the same input and now", () => {
    const a = scoreNewsImportance(item(), { now: NOW });
    const b = scoreNewsImportance(item(), { now: NOW });
    expect(a).toEqual(b);
  });

  it("clamps the score into 0..100", () => {
    const high = scoreNewsImportance(item(), { now: NOW, portfolio: ["SPY"] });
    const low = scoreNewsImportance(
      item({
        headline: "Why this blog likes bonds",
        tier: 4,
        category: "BONDS",
        ticker: null,
        sourceCount: 1,
        timestamp: new Date(NOW - 5 * 24 * 60 * 60_000).toISOString(),
      }),
      { now: NOW },
    );
    expect(high.score).toBeLessThanOrEqual(100);
    expect(low.score).toBeGreaterThanOrEqual(0);
  });
});

describe("rankNewsImportance", () => {
  it("orders strongest first and attaches the result", () => {
    const rows = [
      item({
        headline: "Why 3 stocks could rally",
        tier: 4,
        sourceCount: 1,
        timestamp: new Date(NOW - 3 * 60 * 60_000).toISOString(),
      }),
      item({
        headline: "Fed cuts rates by 50bp",
        timestamp: new Date(NOW - 2 * 60_000).toISOString(),
        sourceCount: 5,
      }),
    ];
    const ranked = rankNewsImportance(rows, { now: NOW });
    expect(ranked[0].headline).toContain("Fed cuts");
    expect(ranked[0].importance.level).toBe("critical");
    expect(ranked[1].importance.score).toBeLessThan(ranked[0].importance.score);
  });
});
