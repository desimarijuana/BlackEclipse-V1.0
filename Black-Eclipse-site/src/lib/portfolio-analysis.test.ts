import { describe, it, expect } from "vitest";
import {
  computeHealthScore,
  buildBrief,
  buildChanges,
  computeAttribution,
  computeStress,
  computeWhatIf,
  computePositionSize,
  computeMonteCarlo,
  type Holding,
  type HoldingMeta,
  type PortfolioTotals,
} from "./portfolio-analysis";

const META: Record<string, HoldingMeta> = {
  BTC: { name: "Bitcoin", category: "Store of Value", dayPct: 2.14, beta: 1.0, vol: 48, sharpe: 1.42, mdd: -32, target: 35 },
  ETH: { name: "Ethereum", category: "Smart Contracts", dayPct: 2.41, beta: 1.18, vol: 62, sharpe: 1.1, mdd: -45, target: 25 },
  SOL: { name: "Solana", category: "Smart Contracts", dayPct: 3.82, beta: 1.55, vol: 88, sharpe: 0.94, mdd: -62, target: 15 },
};

function holding(symbol: string, value: number, qty = 1, avgCost = 100, price = 100): Holding {
  return {
    symbol,
    quantity: qty,
    avgCost,
    currentPrice: price,
    value,
    unrealizedPnL: value - qty * avgCost,
    allocation: 0,
    realizedPnL: 0,
  };
}

const TOTALS: PortfolioTotals = {
  totalValue: 30000,
  costBasis: 25000,
  unrealizedPnL: 5000,
  realizedPnL: 0,
  roiPercent: 20,
  dailyChangeValue: 600,
  dailyChangePercent: 2,
};

describe("computeHealthScore", () => {
  it("returns 0 for an empty portfolio", () => {
    const s = computeHealthScore([], META);
    expect(s.total).toBe(0);
  });

  it("returns 0 diversification for a single holding", () => {
    const s = computeHealthScore([holding("BTC", 10000)], META);
    expect(s.breakdown.diversification).toBe(0);
  });

  it("scores a diversified portfolio higher than a concentrated one", () => {
    const diversified = computeHealthScore(
      [holding("BTC", 10000), holding("ETH", 10000), holding("SOL", 10000)],
      META
    );
    const concentrated = computeHealthScore([holding("BTC", 29000), holding("ETH", 1000)], META);
    expect(diversified.breakdown.diversification).toBeGreaterThan(concentrated.breakdown.diversification);
  });

  it("clamps total score to 0–100", () => {
    const s = computeHealthScore([holding("BTC", 10000)], META);
    expect(s.total).toBeGreaterThanOrEqual(0);
    expect(s.total).toBeLessThanOrEqual(100);
  });

  it("reports valuation and quality as null (unsupported for crypto)", () => {
    const s = computeHealthScore([holding("BTC", 10000)], META);
    expect(s.breakdown.valuation).toBeNull();
    expect(s.breakdown.quality).toBeNull();
  });
});

describe("buildBrief", () => {
  it("handles empty portfolio", () => {
    const lines = buildBrief({ ...TOTALS, totalValue: 0 }, [], META);
    expect(lines[0]).toMatch(/empty/i);
  });

  it("mentions direction of today's move", () => {
    const lines = buildBrief(TOTALS, [holding("BTC", 20000), holding("ETH", 10000)], META);
    expect(lines[0]).toMatch(/up 2\.00% today/);
  });

  it("flags concentration above 40%", () => {
    const lines = buildBrief(TOTALS, [holding("BTC", 25000), holding("ETH", 5000)], META);
    expect(lines.some(l => l.includes("concentration"))).toBe(true);
  });
});

describe("buildChanges", () => {
  it("reports allocation drift vs target", () => {
    // BTC at 66% vs 35% target → large positive drift.
    const changes = buildChanges([holding("BTC", 20000), holding("ETH", 10000)], META);
    expect(changes.some(c => c.symbol === "BTC" && c.text.includes("allocation"))).toBe(true);
  });

  it("caps at 5 items", () => {
    const changes = buildChanges(
      [holding("BTC", 20000), holding("ETH", 10000), holding("SOL", 5000)],
      META
    );
    expect(changes.length).toBeLessThanOrEqual(5);
  });
});

describe("computeAttribution", () => {
  it("sorts by dollar contribution descending", () => {
    const rows = computeAttribution(
      [holding("BTC", 20000, 1, 100, 200), holding("ETH", 10000, 1, 100, 50)],
      20000
    );
    expect(rows[0].symbol).toBe("BTC");
    expect(rows[0].dollar).toBeGreaterThan(rows[1].dollar);
  });
});

describe("computeStress", () => {
  it("produces negative impact for a down scenario", () => {
    const res = computeStress(
      [holding("BTC", 20000), holding("ETH", 10000)],
      META,
      { id: "market", label: "Market −25%", desc: "", mkt: -25, alt: 0 },
      1
    );
    expect(res.dollar).toBeLessThan(0);
    expect(res.worstPct).toBeLessThan(0);
  });

  it("scales with severity", () => {
    const base = computeStress([holding("BTC", 20000)], META, { id: "m", label: "", desc: "", mkt: -10, alt: 0 }, 1);
    const doubled = computeStress([holding("BTC", 20000)], META, { id: "m", label: "", desc: "", mkt: -10, alt: 0 }, 2);
    expect(doubled.dollar).toBeCloseTo(base.dollar * 2, 0);
  });
});

describe("computeWhatIf", () => {
  it("computes new weight for a buy", () => {
    const res = computeWhatIf(
      [holding("BTC", 20000, 100, 100, 200), holding("ETH", 10000, 100, 100, 100)],
      META,
      { symbol: "BTC", side: "Buy", qty: 1, cash: 10000 }
    );
    expect(res.delta).toBe(1);
    expect(res.newWeight).toBeGreaterThan(res.oldWeight);
    expect(res.newCash).toBe(10000 - 200);
  });

  it("caps a sell at held quantity", () => {
    const res = computeWhatIf(
      [holding("BTC", 20000, 1, 100, 200)],
      META,
      { symbol: "BTC", side: "Sell", qty: 5, cash: 10000 }
    );
    expect(res.delta).toBe(-1);
  });

  it("flags high concentration", () => {
    const res = computeWhatIf(
      [holding("BTC", 20000, 1, 100, 200), holding("ETH", 1000, 1, 100, 100)],
      META,
      { symbol: "BTC", side: "Buy", qty: 100, cash: 100000 }
    );
    expect(res.concentration).toBe("HIGH");
  });
});

describe("computePositionSize", () => {
  it("computes units from risk and stop distance", () => {
    const r = computePositionSize({ accountValue: 25000, riskPct: 1, entry: 100, stop: 90, target: 130 });
    expect(r.riskDollar).toBe(250);
    expect(r.units).toBe(25);
    expect(r.maxLoss).toBeCloseTo(250, 5);
    expect(r.rr).toBeCloseTo(3, 5);
  });

  it("returns zero units when stop is at/above entry", () => {
    const r = computePositionSize({ accountValue: 25000, riskPct: 1, entry: 100, stop: 100, target: 130 });
    expect(r.units).toBe(0);
  });
});

describe("computeMonteCarlo", () => {
  it("produces ordered percentiles", () => {
    const r = computeMonteCarlo({ totalValue: 30000, vol: 60, years: 5, monthly: 500 });
    expect(r.end.lo).toBeLessThan(r.end.mid);
    expect(r.end.mid).toBeLessThan(r.end.hi);
    expect(r.months.length).toBe(61);
  });

  it("is deterministic", () => {
    const a = computeMonteCarlo({ totalValue: 30000, vol: 60, years: 5, monthly: 500 });
    const b = computeMonteCarlo({ totalValue: 30000, vol: 60, years: 5, monthly: 500 });
    expect(a.end.mid).toBe(b.end.mid);
  });
});
