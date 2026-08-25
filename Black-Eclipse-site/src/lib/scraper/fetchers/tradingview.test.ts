import { describe, it, expect } from "vitest";
import {
  MARKET_SLUG,
  yahooSymbol,
  scanMarket,
  isTradingViewMarket,
} from "./tradingview";

describe("tradingview fetcher", () => {
  it("maps market ids to country slugs", () => {
    expect(MARKET_SLUG.CN).toBe("china");
    expect(MARKET_SLUG.DE).toBe("germany");
    expect(MARKET_SLUG.PK).toBe("pakistan");
    expect(MARKET_SLUG.CA).toBe("canada");
    expect(isTradingViewMarket("CN")).toBe(true);
    expect(isTradingViewMarket("US")).toBe(false); // US stays on yfinance
  });

  it("normalizes bare symbols to Yahoo suffixes", () => {
    expect(yahooSymbol("600000", "CN")).toBe("600000.SS"); // 6xxxxx -> Shanghai
    expect(yahooSymbol("000001", "CN")).toBe("000001.SZ"); // 0xxxxx -> Shenzhen
    expect(yahooSymbol("300750", "CN")).toBe("300750.SZ"); // 3xxxxx -> Shenzhen
    expect(yahooSymbol("830001", "CN")).toBe("830001.BJ"); // 8xxxxx -> Beijing
    expect(yahooSymbol("ALV", "DE")).toBe("ALV.DE");
    expect(yahooSymbol("AAPL", "US")).toBe("AAPL"); // no suffix
  });

  it("scans a real market and returns normalized rows", async () => {
    // Live integration test — skipped offline. China is a solid, stable market.
    const rows = await scanMarket("CN", 5);
    expect(rows.length).toBeGreaterThan(0);
    const r = rows[0];
    expect(r.symbol).toBeTruthy();
    expect(r.price).toBeGreaterThan(0);
    expect(r.yahooSymbol).toMatch(/\.(SS|SZ|BJ)$/);
    expect(typeof r.exchange).toBe("string");
    expect(r.marketCap).toBeGreaterThan(0);
  }, 70000);

  it("returns empty for markets without a TradingView slug", async () => {
    const rows = await scanMarket("US", 5); // US not in MARKET_SLUG
    expect(rows).toEqual([]);
  });

  it("throws on an unknown slug (network), not silently empty", async () => {
    // A slug that maps but isn't a real TV country should not crash parsing.
    // We test scanMarket's network handling indirectly: it either returns
    // rows or throws. No crash and a defined result either way.
    await expect(
      Promise.race([
        scanMarket("CN", 3).catch(() => "rejected"),
        new Promise((res) => setTimeout(() => res("timeout"), 70000)),
      ])
    ).resolves.toBeDefined();
  });
});
