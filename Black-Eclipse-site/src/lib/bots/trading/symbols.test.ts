import { describe, expect, it } from "vitest";
import {
  candidatesFromFindTrades,
  dedupeCandidates,
  describeScan,
  isSymbolTradable,
  parseSymbols,
  pickUniverse,
  rankEvaluations,
  resolveTradable,
} from "./symbols";

describe("parsing symbols", () => {
  it("splits, upper-cases, de-duplicates and drops junk", () => {
    expect(parseSymbols("eurusd, GBPUSD  eurusd\n!!! XAUUSD.m")).toEqual([
      "EURUSD",
      "GBPUSD",
      "XAUUSD.M",
    ]);
  });

  it("accepts an array and caps at the venue budget", () => {
    const many = Array.from({ length: 20 }, (_, i) => `SYM${i}`);
    expect(parseSymbols(many)).toHaveLength(8);
  });

  it("returns an empty list for empty input — never a placeholder", () => {
    expect(parseSymbols("   ")).toEqual([]);
    expect(parseSymbols([])).toEqual([]);
  });
});

describe("venue tradability", () => {
  const venue = ["EURUSD", "EURUSD.m", "XAUUSD_SB", "BTCUSD-ECN", "EURUSDT"];

  it("matches the exact symbol", () => {
    expect(isSymbolTradable("EURUSD", venue)).toBe(true);
  });

  it("matches a broker suffix", () => {
    expect(isSymbolTradable("EURUSD", ["EURUSD.m"])).toBe(true);
    expect(isSymbolTradable("XAUUSD", ["XAUUSD_SB"])).toBe(true);
    expect(isSymbolTradable("BTCUSD", ["BTCUSD-ECN"])).toBe(true);
  });

  it("never matches a longer symbol that only shares a prefix", () => {
    expect(isSymbolTradable("EURUSD", ["EURUSDT"])).toBe(false);
    expect(isSymbolTradable("BTCUSD", ["BTCUSD2"])).toBe(false);
  });

  it("resolves a strategy universe into tradable + missing + mapping", () => {
    const resolved = resolveTradable(["EURUSD", "USDJPY", "BTCUSD"], venue);
    expect(resolved.tradable).toEqual(["EURUSD", "BTCUSD"]);
    expect(resolved.missing).toEqual(["USDJPY"]);
    expect(resolved.mapping).toEqual({ EURUSD: "EURUSD", BTCUSD: "BTCUSD-ECN" });
  });
});

describe("find-trades candidates", () => {
  it("reads the common field aliases and keeps the best row per symbol", () => {
    const candidates = candidatesFromFindTrades([
      { symbol: "eurusd", score: 0.4, setup: "retest" },
      { ticker: "EURUSD", rank: 9, pattern: "breakout" },
      { instrument: "GBPUSD", confidence: 0.7 },
      { name: "no symbol here" },
    ]);
    expect(candidates).toHaveLength(2);
    expect(candidates[0]).toEqual({
      symbol: "EURUSD",
      score: 9,
      setup: "breakout",
      source: "find-trades",
    });
    expect(candidates[1].symbol).toBe("GBPUSD");
  });

  it("is deterministic and sorted by score", () => {
    const a = dedupeCandidates([
      { symbol: "A", score: 1 },
      { symbol: "B", score: 3 },
      { symbol: "A", score: 5 },
    ]);
    expect(a.map((item) => item.symbol)).toEqual(["A", "B"]);
    expect(a[0].score).toBe(5);
  });

  it("returns nothing rather than inventing a candidate", () => {
    expect(candidatesFromFindTrades([])).toEqual([]);
    expect(candidatesFromFindTrades([{ price: 1 }])).toEqual([]);
  });
});

describe("the scanned universe", () => {
  it("keeps pinned order, then discovery, inside the allowed universe", () => {
    const universe = pickUniverse({
      pinned: ["GBPUSD", "EURUSD"],
      candidates: [
        { symbol: "USDJPY", score: 10 },
        { symbol: "EURUSD", score: 5 },
        { symbol: "AUDUSD", score: 3 },
      ],
      allowed: ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY"],
      excluded: ["AUDUSD"],
      max: 3,
    });
    expect(universe).toEqual(["GBPUSD", "EURUSD", "USDJPY"]);
  });

  it("enforces a strategy's universe when one is given", () => {
    const universe = pickUniverse({
      pinned: ["NAS100"],
      candidates: [{ symbol: "EURUSD", score: 1 }],
      allowed: ["EURUSD"],
    });
    expect(universe).toEqual(["EURUSD"]);
  });

  it("caps at maxSymbols even with more candidates", () => {
    const universe = pickUniverse({
      pinned: [],
      candidates: ["A", "B", "C", "D", "E"].map((symbol, i) => ({ symbol, score: 5 - i })),
      max: 2,
    });
    expect(universe).toEqual(["A", "B"]);
  });
});

describe("ranking a multi-symbol scan", () => {
  it("puts exits first, ranks entries by score, and never stacks a held symbol", () => {
    const picked = rankEvaluations(
      [
        { symbol: "EURUSD", signal: "long_entry", score: 0.9, reason: "cross" },
        { symbol: "GBPUSD", signal: "long_exit", score: 0.1, reason: "cross down" },
        { symbol: "AUDUSD", signal: "long_entry", score: 0.95, reason: "held" },
        { symbol: "USDJPY", signal: "short_entry", score: 0.8, reason: "break" },
        { symbol: "NZDUSD", signal: "none", score: 0, reason: "—" },
      ],
      { openSymbols: ["AUDUSD"], maxPositions: 1 },
    );
    expect(picked.map((item) => item.symbol)).toEqual([
      "GBPUSD",
      "EURUSD",
    ]);
    expect(picked.map((item) => item.signal)).toEqual(["long_exit", "long_entry"]);
  });

  it("returns an empty list when nothing is actionable", () => {
    expect(
      rankEvaluations([{ symbol: "EURUSD", signal: "none", score: 0, reason: "—" }]),
    ).toEqual([]);
  });

  it("describes a scan honestly", () => {
    expect(describeScan([], [])).toMatch(/No symbols/);
    expect(describeScan(["EURUSD", "GBPUSD"], [])).toMatch(/no actionable signal/);
    expect(
      describeScan(
        ["EURUSD", "GBPUSD"],
        [{ symbol: "GBPUSD", signal: "long_entry", score: 1, reason: "x" }],
      ),
    ).toContain("GBPUSD long_entry");
  });
});
