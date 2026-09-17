import { describe, it, expect } from "vitest";
import { computePortfolioStats } from "./use-portfolio-engine";
import type { Transaction } from "@/lib/portfolio/types";

// ── JDDS asset flow tests ────────────────────────────────────────────────────
// A user can add ANY asset from the JDDS database (US, PK, IN, CN, CRYPTO, ...)
// to their portfolio. The engine produces holdings in native currency, plus
// USD-equivalent aggregates via the live fxToUsd rate — regardless of market.

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
      [{ symbol: "AAPL", price: 313.45, changePercent: 1.2, currency: "USD", fxToUsd: 1 }]
    );
    expect(stats.holdings).toHaveLength(1);
    const h = stats.holdings[0];
    expect(h.symbol).toBe("AAPL");
    expect(h.quantity).toBe(10);
    expect(h.currentPrice).toBe(313.45);
    expect(h.value).toBeCloseTo(3134.5, 2);
    expect(h.valueUsd).toBeCloseTo(3134.5, 2);
    expect(h.avgCost).toBeCloseTo(300.5, 2);
    expect(h.unrealizedPnL).toBeCloseTo(129.5, 2);
    expect(h.allocation).toBe(100);
    expect(stats.totalValue).toBeCloseTo(3134.5, 2);
  });

  it("values a PKR stock (OGDC) in native currency and converts at the live FX rate", () => {
    const fxToUsd = 1 / 278.5;
    const stats = computePortfolioStats(
      [tx({ symbol: "OGDC", quantity: 500, price: 300, fee: 50 })],
      [{ symbol: "OGDC", price: 327.43, changePercent: -0.34, currency: "PKR", fxToUsd }]
    );
    const h = stats.holdings[0];
    expect(h.symbol).toBe("OGDC");
    expect(h.currentPrice).toBe(327.43);
    expect(h.value).toBeCloseTo(163715, 2);          // native PKR
    expect(h.valueUsd).toBeCloseTo(163715 * fxToUsd, 2);
    expect(h.unrealizedPnL).toBeCloseTo(13665, 2);   // native PKR
    expect(h.unrealizedPnLUsd).toBeCloseTo(13665 * fxToUsd, 2);
  });

  it("mixes crypto + PKR equities and computes allocations on USD-equivalents", () => {
    const fxToUsd = 1 / 278;
    const stats = computePortfolioStats(
      [
        tx({ symbol: "BTC", quantity: 0.25, price: 61500, fee: 15 }),
        tx({ symbol: "OGDC", quantity: 500, price: 300, fee: 50 }),
      ],
      [
        { symbol: "BTC", price: 78900.68, changePercent: 2.1, currency: "USD", fxToUsd: 1 },
        { symbol: "OGDC", price: 327.43, changePercent: -0.34, currency: "PKR", fxToUsd },
      ]
    );
    expect(stats.holdings).toHaveLength(2);
    const btcUsd = 0.25 * 78900.68;
    const ogdcUsd = 163715 * fxToUsd;
    expect(stats.totalValue).toBeCloseTo(btcUsd + ogdcUsd, 2);
    const bySymbol = new Map(stats.holdings.map(h => [h.symbol, h]));
    expect(bySymbol.get("BTC")!.allocation).toBeCloseTo((btcUsd / (btcUsd + ogdcUsd)) * 100, 4);
  });

  it("handles a symbol with no live quote yet (price 0) without crashing", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "NEWCO", quantity: 100, price: 50 })],
      []
    );
    expect(stats.holdings).toHaveLength(1);
    expect(stats.holdings[0].currentPrice).toBe(0);
    expect(stats.holdings[0].value).toBe(0);
    expect(stats.totalValue).toBe(0);
  });

  it("applies FIFO lot matching with correct realized P/L", () => {
    const stats = computePortfolioStats(
      [
        tx({ symbol: "UBL", quantity: 150, price: 300, fee: 45, date: "2026-05-12" }),
        tx({ symbol: "UBL", quantity: 80, price: 338, fee: 28, date: "2026-07-20" }),
        tx({ symbol: "UBL", type: "SELL", quantity: 50, price: 400, fee: 15, date: "2026-08-18" }),
      ],
      [{ symbol: "UBL", price: 456.97, changePercent: 0.6, currency: "PKR", fxToUsd: 1 / 278 }]
    );
    const h = stats.holdings[0];
    expect(h.symbol).toBe("UBL");
    expect(h.quantity).toBe(180); // 150 + 80 - 50
    // FIFO: sell 50 from the 150 @ 300 lot → cost of sold = 50*300 = 15000
    // remaining cost basis = (150*300+45) + (80*338+28) - 15000 = 57113
    expect(h.avgCost).toBeCloseTo(57113 / 180, 4);
    expect(h.value).toBeCloseTo(180 * 456.97, 2);
    // Realized: proceeds 50*400-15=19985 minus cost 15000 = 4985
    expect(stats.realizedPnL).toBeCloseTo(4985 / 278, 2);
  });

  it("computes daily change from the live changePercent", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "AAPL", quantity: 10, price: 300 })],
      [{ symbol: "AAPL", price: 313.45, changePercent: 1.2, currency: "USD", fxToUsd: 1 }]
    );
    // prevPrice = 313.45 / 1.012 = 309.73...; dayChange = 10*(313.45-309.73)
    const prevPrice = 313.45 / 1.012;
    expect(stats.dailyChangeValue).toBeCloseTo(10 * (313.45 - prevPrice), 2);
    expect(stats.dailyChangePercent).toBeGreaterThan(0);
  });

  it("keeps defaultValue FX fallback for PKR assets when fxToUsd is absent", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "MEBL", quantity: 100, price: 180 })],
      [{ symbol: "MEBL", price: 185.25, changePercent: 0.85, currency: "PKR" }]
    );
    const h = stats.holdings[0];
    expect(h.value).toBeCloseTo(18525, 2);
    expect(h.valueUsd).toBeCloseTo(18525 / 278, 2);
    // …and the row is flagged so the UI can call that USD value an estimate.
    expect(h.fxMissing).toBe(true);
  });

  it("uses a live FX rate for any non-USD currency, not just PKR", () => {
    // An Indian holding must convert at the real rate. The old code only knew
    // USD/PKR and would value this 1:1 against the dollar.
    const stats = computePortfolioStats(
      [tx({ symbol: "RELIANCE", quantity: 10, price: 1100 })],
      [{ symbol: "RELIANCE", price: 1235.3, changePercent: 1.1, currency: "INR", fxToUsd: 1 / 87 }]
    );
    const h = stats.holdings[0];
    expect(h.currency).toBe("INR");
    expect(h.value).toBeCloseTo(12353, 2);
    expect(h.valueUsd).toBeCloseTo(12353 / 87, 2);
    expect(h.fxMissing).toBe(false);
  });

  it("does not flag USD positions as missing FX", () => {
    const stats = computePortfolioStats(
      [tx({ symbol: "AAPL", quantity: 1, price: 100 })],
      [{ symbol: "AAPL", price: 110, changePercent: 0, currency: "USD" }]
    );
    expect(stats.holdings[0].fxMissing).toBe(false);
    expect(stats.holdings[0].fxToUsd).toBe(1);
  });

  it("values a mixed USD + INR + PKR book in a common USD base", () => {
    const stats = computePortfolioStats(
      [
        tx({ symbol: "AAPL", quantity: 1, price: 100 }),
        tx({ symbol: "RELIANCE", quantity: 87, price: 1000 }),
        tx({ symbol: "MEBL", quantity: 278, price: 100 }),
      ],
      [
        { symbol: "AAPL", price: 100, changePercent: 0, currency: "USD", fxToUsd: 1 },
        { symbol: "RELIANCE", price: 100, changePercent: 0, currency: "INR", fxToUsd: 1 / 87 },
        { symbol: "MEBL", price: 100, changePercent: 0, currency: "PKR", fxToUsd: 1 / 278 },
      ]
    );
    // Each converts to 100 USD, so the book is 300 USD with 3 equal weights.
    expect(stats.totalValue).toBeCloseTo(300, 6);
    expect(stats.holdings).toHaveLength(3);
    for (const h of stats.holdings) {
      expect(h.valueUsd).toBeCloseTo(100, 6);
      expect(h.allocation).toBeCloseTo(100 / 3, 6);
    }
  });
});
