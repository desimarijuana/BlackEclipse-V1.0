import { describe, it, expect, vi, beforeEach } from "vitest";

// Phase-2 bridge capabilities reach existing live providers and the shared
// web-research transport. Those are mocked here so the tests are offline and
// assert the bridge's own mapping, not a provider.

const fetchQuoteWithFallback = vi.fn();
const fetchYahooBatchRaw = vi.fn();
const webSearch = vi.fn();
const fetchWebPage = vi.fn();

vi.mock("@/lib/db", () => ({ prisma: {} }));
vi.mock("@/lib/scraper/fetchers", () => ({
  fetchQuoteWithFallback: (...a: unknown[]) => fetchQuoteWithFallback(...a),
}));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: (...a: unknown[]) => fetchYahooBatchRaw(...a),
}));
// Use the REAL normalizer so the test catches the { date, value } contract
// between the macro sources and the normalizer (the FRED-analytics regression).
vi.mock("@/lib/economics/fetch", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/economics/fetch")>();
  return actual;
});
vi.mock("@/lib/economics/sources", () => ({
  getSource: (id: string) =>
    id === "fred-analytics"
      ? {
          id,
          label: "FRED Analytics",
          controls: [{ name: "seriesId", defaultValue: "GDP" }],
          // Mirrors the real source's canonical { date, value } output.
          fetch: async () => [{ date: "2026-08-01", value: "3.1" }],
        }
      : undefined,
}));
vi.mock("@/lib/web-research", () => ({
  webSearch: (...a: unknown[]) => webSearch(...a),
  fetchWebPage: (...a: unknown[]) => fetchWebPage(...a),
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  fetchQuoteWithFallback.mockReset();
  fetchYahooBatchRaw.mockReset();
  webSearch.mockReset();
  fetchWebPage.mockReset();
});

describe("fetchCapability — live_quote", () => {
  it("maps a live quote and records the provider", async () => {
    fetchQuoteWithFallback.mockResolvedValue({
      status: "ok",
      source: "yfinance",
      quote: { symbol: "AAPL", price: 240.1, changePct: 1.2, volume: 10, marketCap: 3e12 },
    });
    const result = await fetchCapability("live_quote", { symbol: "aapl", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.provider).toBe("yfinance");
    expect((result.price as { price: number }).price).toBe(240.1);
  });

  it("returns UNAVAILABLE when the provider fails (never fabricates)", async () => {
    fetchQuoteWithFallback.mockResolvedValue({ status: "network_error", error: "down", source: "yfinance" });
    const result = await fetchCapability("live_quote", { symbol: "AAPL" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result).not.toHaveProperty("price");
  });
});

describe("fetchCapability — price_history", () => {
  it("returns a real series from the batched bridge", async () => {
    fetchYahooBatchRaw.mockResolvedValue({ history: { "AAPL": [{ date: "2026-09-18", close: 1 }, { date: "2026-09-19", close: 2 }] } });
    const result = await fetchCapability("price_history", { symbol: "AAPL", period: "1mo" });
    expect(result.status).toBe("OK");
    expect((result.series as unknown[]).length).toBe(2);
  });

  it("returns UNAVAILABLE when no series is available", async () => {
    fetchYahooBatchRaw.mockRejectedValue(new Error("offline"));
    const result = await fetchCapability("price_history", { symbol: "AAPL" });
    expect(result.status).toBe("UNAVAILABLE");
  });
});

describe("fetchCapability — macro_series", () => {
  it("normalizes macro rows from an existing source", async () => {
    const result = await fetchCapability("macro_series", { source: "fred-analytics", series: "GDP" });
    expect(result.status).toBe("OK");
    expect((result.rows as unknown[]).length).toBe(1);
  });

  it("rejects an unknown macro source", async () => {
    const result = await fetchCapability("macro_series", { source: "nope" });
    expect(result.status).toBe("UNAVAILABLE");
  });
});

describe("macro source ↔ normalizer contract", () => {
  it("the real normalizer accepts the canonical { date, value } shape", async () => {
    const { normalizeEconomicSeries } = await import("@/lib/economics/fetch");
    // What every macro source now emits (FRED-analytics previously emitted
    // dynamic-header rows that normalized to zero observations).
    const rows = normalizeEconomicSeries(
      [
        { date: "2026-06-01", value: "3.1" },
        { date: "2026-07-01", value: "3.2" },
      ],
      "fred-analytics"
    );
    expect(rows.length).toBe(2);
    expect(rows[0].value).toBe(3.1);
    expect(rows[1].date).toBe("2026-07-01");
  });
});

describe("fetchCapability — web research (shared transport)", () => {
  it("web_search returns results", async () => {
    webSearch.mockResolvedValue([{ title: "t", url: "https://x", snippet: "s", publishedAt: null }]);
    const result = await fetchCapability("web_search", { query: "q" });
    expect(result.status).toBe("OK");
    expect((result.results as unknown[]).length).toBe(1);
  });

  it("web_search UNAVAILABLE when nothing is found", async () => {
    webSearch.mockResolvedValue([]);
    const result = await fetchCapability("web_search", { query: "q" });
    expect(result.status).toBe("UNAVAILABLE");
  });

  it("web_fetch returns page text", async () => {
    fetchWebPage.mockResolvedValue({ url: "https://x", title: "t", text: "body", bytes: 4 });
    const result = await fetchCapability("web_fetch", { url: "https://x" });
    expect(result.status).toBe("OK");
    expect(result.text).toBe("body");
  });

  it("web_fetch UNAVAILABLE when the page cannot be retrieved", async () => {
    fetchWebPage.mockResolvedValue(null);
    const result = await fetchCapability("web_fetch", { url: "https://x" });
    expect(result.status).toBe("UNAVAILABLE");
  });
});
