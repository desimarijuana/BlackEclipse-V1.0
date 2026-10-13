import { describe, it, expect, vi, beforeEach } from "vitest";

// The SECOND price-history transport (R3-04 follow-up): the direct Yahoo chart
// request. Offline: the chart helper is mocked; the candidate chain is the
// module's own logic under test.

const fetchYahooChartSeries = vi.fn();
const yahooChartCandidates = vi.fn();

vi.mock("@/lib/scraper/yahoo-chart", () => ({
  fetchYahooChartSeries: (...a: unknown[]) => fetchYahooChartSeries(...a),
  yahooChartCandidates: (...a: unknown[]) => yahooChartCandidates(...a),
}));

import { fetchHistorySeriesFallback } from "./data-bridge-history";

beforeEach(() => {
  fetchYahooChartSeries.mockReset();
  yahooChartCandidates.mockReset();
});

describe("fetchHistorySeriesFallback", () => {
  it("tries the candidate chain in order and returns the first real series", async () => {
    yahooChartCandidates.mockReturnValue(["FFC.KA", "FFC"]);
    fetchYahooChartSeries
      .mockResolvedValueOnce({ bars: [{ date: "2026-09-18", close: 315.91 }], meta: {} }) // 1 bar → too thin
      .mockResolvedValueOnce({
        bars: [{ date: "2026-09-18", close: 315.91 }, { date: "2026-09-19", close: 318.2 }],
        meta: {},
      });
    const result = await fetchHistorySeriesFallback("FFC", "PK", "1mo", "1d");
    expect(result).not.toBeNull();
    expect(result!.ticker).toBe("FFC");
    expect(result!.provider).toBe("yfinance");
    expect(result!.transport).toBe("yahoo-chart");
    expect(result!.series).toHaveLength(2);
    expect(fetchYahooChartSeries).toHaveBeenNthCalledWith(1, "FFC.KA", "1mo", "1d");
    expect(fetchYahooChartSeries).toHaveBeenNthCalledWith(2, "FFC", "1mo", "1d");
  });

  it("returns null when no candidate yields at least two bars", async () => {
    yahooChartCandidates.mockReturnValue(["AAPL"]);
    fetchYahooChartSeries.mockResolvedValue(null);
    expect(await fetchHistorySeriesFallback("AAPL", "US", "1y", "1d")).toBeNull();
  });

  it("never invents a series from a single point", async () => {
    yahooChartCandidates.mockReturnValue(["AAPL"]);
    fetchYahooChartSeries.mockResolvedValue({ bars: [{ date: "2026-09-18", close: 1 }], meta: {} });
    expect(await fetchHistorySeriesFallback("AAPL", "US", "1y", "1d")).toBeNull();
  });
});
