import { describe, it, expect, vi } from "vitest";

// The candle cache stores full OHLC, but OPEN/HIGH/LOW conditions used to be
// classified as snapshot-only — and no snapshot ever carried OHL (TradingView
// scan rows have none), so those alerts could only ever report an error. They
// are now candle-backed and exposed from the cache.

const ROWS = [
  { o: 1, h: 2, l: 0.5, c: 1.5, v: 10 },
  { o: 2, h: 4, l: 1.5, c: 3, v: 20 },
  { o: 3, h: 5, l: 2.5, c: 4, v: 30 },
];

vi.mock("@/lib/db", () => ({
  prisma: { candles: { findMany: vi.fn(async () => ROWS), count: vi.fn(async () => ROWS.length) } },
}));
vi.mock("@/lib/scraper/fetchers/tradingview", () => ({ getCachedMarketScan: vi.fn(async () => []) }));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: vi.fn(async () => ({ quotes: {} })),
  yahooSymbol: (s: string) => s,
}));

import { indicatorWindow } from "./dataFeeds";
import { needsCandles } from "./conditionEvaluator";

const leaf = (indicator: string) => [{ indicator, operator: ">", compareMode: "value", value: 1 }];

describe("alert data feeds — OPEN/HIGH/LOW", () => {
  it("classifies OPEN/HIGH/LOW as candle-backed", () => {
    expect(needsCandles(leaf("HIGH"))).toBe(true);
    expect(needsCandles(leaf("LOW"))).toBe(true);
    expect(needsCandles(leaf("OPEN"))).toBe(true);
    // A pure quote watch must NOT require candle warmup.
    expect(needsCandles(leaf("CLOSE"))).toBe(false);
  });

  it("exposes OPEN/HIGH/LOW series from the candle cache", async () => {
    const w = await indicatorWindow("AAPL", "1d", leaf("HIGH"));
    expect(w.get("HIGH()")).toEqual([2, 4, 5]);
    const wo = await indicatorWindow("AAPL", "1d", leaf("OPEN"));
    expect(wo.get("OPEN()")).toEqual([1, 2, 3]);
    const wl = await indicatorWindow("AAPL", "1d", leaf("LOW"));
    expect(wl.get("LOW()")).toEqual([0.5, 1.5, 2.5]);
  });
});
