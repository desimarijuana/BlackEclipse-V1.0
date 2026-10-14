import { describe, it, expect, vi, beforeEach } from "vitest";

// The Yahoo market-data provider must HONOR a requested window. It used to map
// any `start` to range "max" and ignore `end`, so a Dec-2025 window returned the
// whole history and the caller truncated head+tail. Offline: the two transports
// are mocked; the window math is the REAL module code.

const fetchYahooBatchRaw = vi.fn();
const fetchYahooChartSeries = vi.fn();

vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: (...a: unknown[]) => fetchYahooBatchRaw(...a),
}));
vi.mock("@/lib/scraper/yahoo-chart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/scraper/yahoo-chart")>();
  return {
    ...actual,
    fetchYahooChartSeries: (...a: unknown[]) => fetchYahooChartSeries(...a),
  };
});

import { yahooProvider } from "./yahoo";

beforeEach(() => {
  fetchYahooBatchRaw.mockReset();
  fetchYahooChartSeries.mockReset();
});

describe("yahoo provider — requested windows", () => {
  it("picks the smallest covering range and filters bridge rows to the window", async () => {
    fetchYahooBatchRaw.mockResolvedValue({
      history: {
        AAPL: [
          { date: "2025-11-15", close: 100 },
          { date: "2025-12-10", close: 110 },
          { date: "2025-12-31", close: 120 },
          { date: "2026-01-05", close: 130 },
        ],
      },
    });
    const out = await yahooProvider.fetch({
      capability: "historical",
      symbol: "AAPL",
      market: "US",
      interval: "1d",
      start: "2025-12-01",
      end: "2025-12-31",
    } as never);
    // 31 days → "1mo", NOT "max".
    expect(fetchYahooBatchRaw).toHaveBeenCalledWith(["AAPL"], "US", "1d", "1mo");
    const series = out.series as Array<{ timestamp: string }>;
    expect(series.map((s) => s.timestamp)).toEqual(["2025-12-10", "2025-12-31"]);
  });

  it("passes the window through to the direct chart transport when the bridge has no series", async () => {
    fetchYahooBatchRaw.mockRejectedValue(new Error("offline"));
    fetchYahooChartSeries.mockResolvedValue({
      bars: [
        { date: "2025-12-02", close: 1 },
        { date: "2025-12-31", close: 2 },
      ],
      meta: {},
    });
    const out = await yahooProvider.fetch({
      capability: "ohlcv",
      symbol: "AAPL",
      market: "US",
      interval: "1d",
      start: "2025-12-01",
      end: "2025-12-31",
    } as never);
    expect(fetchYahooChartSeries).toHaveBeenCalledWith("AAPL", "1mo", "1d", {
      start: "2025-12-01",
      end: "2025-12-31",
    });
    expect((out.series as unknown[]).length).toBe(2);
  });

  it("keeps the interval default when no window is requested", async () => {
    fetchYahooBatchRaw.mockResolvedValue({
      history: { AAPL: [{ date: "2026-09-18", close: 1 }, { date: "2026-09-19", close: 2 }] },
    });
    await yahooProvider.fetch({ capability: "historical", symbol: "AAPL", market: "US" } as never);
    expect(fetchYahooBatchRaw).toHaveBeenCalledWith(["AAPL"], "US", "1d", "1y");
  });
});
