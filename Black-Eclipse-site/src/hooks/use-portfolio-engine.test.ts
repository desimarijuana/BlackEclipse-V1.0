import { describe, it, expect } from "vitest";
import { computePortfolioStats } from "./use-portfolio-engine";
import type { Transaction } from "@/components/screens/my-portfolio";

// ── JDDS asset flow tests ────────────────────────────────────────────────────
// A user can add ANY asset from the JDDS database (US, PK, IN, CN, CRYPTO, ...)
// to their portfolio. The engine must produce a holding with the live JDDS
// price, correct value, allocation, and P/L — regardless of which market the
// asset belongs to.

const tx = (over: Partial<Transaction>): Transaction => ({
  id: "tx-" + Math.random().toString(36).slice(2),
  type: "BUY",
  symbol: "X",
  quantity: 1,
  price: 100,
  fee: 0,
  date: "2026-01-01",
  ...over,
});

describe("computePortfolioStats with JDDS assets", () => {
  it("values a US stock (AAPL) added from JDDS at its live price", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "AAPL", quantity: 10, price: 300, fee: 5 })],
      [{ symbol: "AAPL", price: 313.45, changePercent: 1.2 }]
    );
    expect(stats.holdings).toHaveLength(1);
    const h = stats.holdings[0];
    expect(h.symbol).toBe("AAPL");
    expect(h.quantity).toBe(10);
    expect(h.currentPrice).toBe(313.45);
    expect(h.value).toBeCloseTo(3134.5, 2);
    expect(h.avgCost).toBeCloseTo(300.5, 2);
    expect(h.unrealizedPnL).toBeCloseTo(129.5, 2);
    expect(h.allocation).toBe(100);
    expect(stats.totalValue).toBeCloseTo(3134.5, 2);
  });

  it("values a PKR stock (OGDC) added from JDDS at its live PKR price", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "OGDC", quantity: 500, price: 300, fee: 50 })],
      [{ symbol: "OGDC", price: 327.43, changePercent: -0.34 }]
    );
    const h = stats.holdings[0];
    expect(h.symbol).toBe("OGDC");
    expect(h.currentPrice).toBe(327.43);
    expect(h.value).toBeCloseTo(163715, 2);
    expect(h.unrealizedPnL).toBeCloseTo(13665, 2);
  });

  it("values an Indian stock (RELIANCE) added from JDDS", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "RELIANCE", quantity: 20, price: 1200, fee: 10 })],
      [{ symbol: "RELIANCE", price: 1299, changePercent: 0.5 }]
    );
    const h = stats.holdings[0];
    expect(h.currentPrice).toBe(1299);
    expect(h.value).toBeCloseTo(25980, 2);
  });

  it("mixes crypto + JDDS equities and computes correct allocations", () => {
    const stats = computePortfolioStats(
      [
        tx({ symbol: "BTC", quantity: 0.25, price: 61500, fee: 15 }),
        tx({ symbol: "AAPL", quantity: 10, price: 300, fee: 5 }),
        tx({ symbol: "OGDC", quantity: 500, price: 300, fee: 50 }),
      ],
      [
        { symbol: "BTC", price: 78900.68, changePercent: 2.1 },
        { symbol: "AAPL", price: 313.45, changePercent: 1.2 },
        { symbol: "OGDC", price: 327.43, changePercent: -0.34 },
      ]
    );
    expect(stats.holdings).toHaveLength(3);
    const total = stats.totalValue;
    expect(total).toBeCloseTo(0.25 * 78900.68 + 3134.5 + 163715, 2);
    for (const h of stats.holdings) {
      expect(h.allocation).toBeCloseTo((h.value / total) * 100, 4);
    }
    // Sorted by value descending: OGDC (163,715) > BTC (19,725) > AAPL (3,134)
    expect(stats.holdings[0].symbol).toBe("OGDC");
    expect(stats.holdings[1].symbol).toBe("BTC");
    expect(stats.holdings[2].symbol).toBe("AAPL");
  });

  it("handles a symbol with no live quote yet (price 0) without crashing", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "NEWCO", quantity: 100, price: 50 })],
      [] // no live data yet
    );
    expect(stats.holdings).toHaveLength(1);
    expect(stats.holdings[0].currentPrice).toBe(0);
    expect(stats.holdings[0].value).toBe(0);
    expect(stats.totalValue).toBe(0);
  });

  it("applies FIFO lot matching for a JDDS asset with multiple buys and a sell", () => {
    const stats = computePortfolioStats(
      [
        tx({ symbol: "UBL", quantity: 150, price: 300, fee: 45, date: "2026-05-12" }),
        tx({ symbol: "UBL", quantity: 80, price: 338, fee: 28, date: "2026-07-20" }),
        tx({ symbol: "UBL", type: "SELL", quantity: 50, price: 400, fee: 15, date: "2026-08-18" }),
      ],
      [{ symbol: "UBL", price: 456.97, changePercent: 0.6 }]
    );
    const h = stats.holdings[0];
    expect(h.symbol).toBe("UBL");
    expect(h.quantity).toBe(180); // 150 + 80 - 50
    // FIFO: sell 50 from the 150 @ 300 lot → cost of sold = 50*300 = 15000
    // remaining cost basis = (150*300+45) + (80*338+28) - 15000 = 45045 + 27068 - 15000 = 57113
    expect(h.avgCost).toBeCloseTo(57113 / 180, 4);
    expect(h.value).toBeCloseTo(180 * 456.97, 2);
    // Realized: proceeds 50*400-15=19985 minus cost 15000 = 4985
    expect(stats.realizedPnL).toBeCloseTo(4985, 2);
  });

  it("computes daily change from the live changePercent for JDDS assets", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "AAPL", quantity: 10, price: 300 })],
      [{ symbol: "AAPL", price: 313.45, changePercent: 1.2 }]
    );
    // prevPrice = 313.45 / 1.012 = 309.73...; dayChange = 10*(313.45-309.73)
    const prevPrice = 313.45 / 1.012;
    expect(stats.dailyChangeValue).toBeCloseTo(10 * (313.45 - prevPrice), 2);
    expect(stats.dailyChangePercent).toBeGreaterThan(0);
  });
});
