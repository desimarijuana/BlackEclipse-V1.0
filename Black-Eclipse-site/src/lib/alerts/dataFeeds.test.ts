import { describe, it, expect, vi, beforeEach } from "vitest";

// The candle cache stores full OHLC, but OPEN/HIGH/LOW conditions used to be
// classified as snapshot-only — and no snapshot ever carried OHL (TradingView
// scan rows have none), so those alerts could only ever report an error. They
// are now candle-backed and exposed from the cache. The watch's `dataSource`
// also now actually selects the feed.

const ROWS = [
  { o: 1, h: 2, l: 0.5, c: 1.5, v: 10 },
  { o: 2, h: 4, l: 1.5, c: 3, v: 20 },
  { o: 3, h: 5, l: 2.5, c: 4, v: 30 },
];

const getCachedMarketScan = vi.fn(async (..._a: unknown[]) => [] as Array<Record<string, unknown>>);
const fetchYahooBatchRaw = vi.fn(async (..._a: unknown[]) => ({ quotes: {} as Record<string, Record<string, unknown>> }));

vi.mock("@/lib/db", () => ({
  prisma: { candles: { findMany: vi.fn(async () => ROWS), count: vi.fn(async () => ROWS.length) } },
}));
vi.mock("@/lib/scraper/fetchers/tradingview", () => ({
  getCachedMarketScan: (...a: unknown[]) => getCachedMarketScan(...a),
}));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: (...a: unknown[]) => fetchYahooBatchRaw(...a),
  yahooSymbol: (s: string) => s,
}));

import { fetchSnapshots, indicatorWindow, normalizeDataSource } from "./dataFeeds";
import { needsCandles } from "./conditionEvaluator";

const leaf = (indicator: string) => [{ indicator, operator: ">", compareMode: "value", value: 1 }];

const TV_ROW = { symbol: "AAPL", exchange: "", name: "Apple", price: 100, changePct: 1, yahooSymbol: "AAPL" };
const BRIDGE = { quotes: { TSLA: { price: 200, changePct: 2 } } };

beforeEach(() => {
  getCachedMarketScan.mockReset();
  fetchYahooBatchRaw.mockReset();
  getCachedMarketScan.mockResolvedValue([TV_ROW]);
  fetchYahooBatchRaw.mockResolvedValue(BRIDGE);
});

describe("alert data feeds — OPEN/HIGH/LOW", () => {
  it("classifies OPEN/HIGH/LOW as candle-backed", () => {
    expect(needsCandles(leaf("HIGH"))).toBe(true);
    expect(needsCandles(leaf("LOW"))).toBe(true);
    expect(needsCandles(leaf("OPEN"))).toBe(true);
    // A pure quote watch must NOT require candle warmup.
    expect(needsCandles(leaf("CLOSE"))).toBe(false);
  });

  it("exposes OPEN/HIGH/LOW series from the candle cache", async () => {
    expect((await indicatorWindow("AAPL", "1d", leaf("HIGH"))).get("HIGH()")).toEqual([2, 4, 5]);
    expect((await indicatorWindow("AAPL", "1d", leaf("OPEN"))).get("OPEN()")).toEqual([1, 2, 3]);
    expect((await indicatorWindow("AAPL", "1d", leaf("LOW"))).get("LOW()")).toEqual([0.5, 1.5, 2.5]);
  });
});

describe("alert data feeds — dataSource selection", () => {
  it("normalizes unknown sources to Auto", () => {
    expect(normalizeDataSource("tradingview")).toBe("TradingView");
    expect(normalizeDataSource("yfinance")).toBe("yfinance");
    expect(normalizeDataSource("nonsense")).toBe("Auto");
    expect(normalizeDataSource(null)).toBe("Auto");
  });

  it("Auto: TradingView first, yfinance bridge for the rest", async () => {
    const snaps = await fetchSnapshots("US", ["AAPL", "TSLA"], "Auto");
    expect(snaps.get("AAPL")?.close).toBe(100);
    expect(snaps.get("TSLA")?.close).toBe(200);
    expect(fetchYahooBatchRaw).toHaveBeenCalledTimes(1);
  });

  it("TradingView: uses only the scan, never the bridge", async () => {
    const snaps = await fetchSnapshots("US", ["AAPL", "TSLA"], "TradingView");
    expect(snaps.has("AAPL")).toBe(true);
    expect(snaps.has("TSLA")).toBe(false);
    expect(fetchYahooBatchRaw).not.toHaveBeenCalled();
  });

  it("yfinance: skips the scan and uses only the bridge", async () => {
    const snaps = await fetchSnapshots("US", ["AAPL", "TSLA"], "yfinance");
    expect(getCachedMarketScan).not.toHaveBeenCalled();
    expect(snaps.has("TSLA")).toBe(true);
    expect(snaps.has("AAPL")).toBe(false);
  });
});
