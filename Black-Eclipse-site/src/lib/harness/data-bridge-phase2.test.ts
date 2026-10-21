import { describe, it, expect, vi, beforeEach } from "vitest";

// Phase-2 bridge capabilities reach existing live providers and the shared
// web-research transport. Those are mocked here so the tests are offline and
// assert the bridge's own mapping, not a provider.

const fetchQuoteWithFallback = vi.fn();
const fetchYahooBatchRaw = vi.fn();
const fetchYahooChartSeries = vi.fn();
const yahooChartCandidates = vi.fn();
const webSearch = vi.fn();
const fetchWebPage = vi.fn();
const searchWeb = vi.fn();
const fetchWebPageDetailed = vi.fn();
const resolveProviderKey = vi.fn();
// Identity resolution now reads the instrument master before any live fetch, so
// the bridge needs the asset lookup. Tests seed one unambiguous US instrument.
const assetFindMany = vi.fn();
const assetFindFirst = vi.fn();
const newsFindMany = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findMany: (...a: unknown[]) => assetFindMany(...a),
      findFirst: (...a: unknown[]) => assetFindFirst(...a),
    },
    newsItem: {
      findMany: (...a: unknown[]) => newsFindMany(...a),
    },
  },
}));
vi.mock("@/lib/scraper/fetchers", () => ({
  fetchQuoteWithFallback: (...a: unknown[]) => fetchQuoteWithFallback(...a),
}));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: (...a: unknown[]) => fetchYahooBatchRaw(...a),
}));
// The DIRECT chart transport (the price-history fallback). Mocked like every
// other provider so the suite is offline; `null` = the transport is down.
vi.mock("@/lib/scraper/yahoo-chart", async (importOriginal) => {
  // The REAL window helpers (pure date math) stay in place.
  const actual = await importOriginal<typeof import("@/lib/scraper/yahoo-chart")>();
  return {
    ...actual,
    fetchYahooChartSeries: (...a: unknown[]) => fetchYahooChartSeries(...a),
    yahooChartCandidates: (...a: unknown[]) => yahooChartCandidates(...a),
  };
});
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
  searchWeb: (...a: unknown[]) => searchWeb(...a),
  fetchWebPageDetailed: (...a: unknown[]) => fetchWebPageDetailed(...a),
}));
vi.mock("@/lib/provider-keys", () => ({
  resolveProviderKey: (...a: unknown[]) => resolveProviderKey(...a),
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  fetchQuoteWithFallback.mockReset();
  fetchYahooBatchRaw.mockReset();
  fetchYahooChartSeries.mockReset();
  yahooChartCandidates.mockReset();
  yahooChartCandidates.mockImplementation((sym: string) => [sym]);
  fetchYahooChartSeries.mockResolvedValue(null);
  webSearch.mockReset();
  fetchWebPage.mockReset();
  searchWeb.mockReset();
  fetchWebPageDetailed.mockReset();
  resolveProviderKey.mockReset();
  resolveProviderKey.mockResolvedValue(null);
  assetFindMany.mockReset();
  assetFindFirst.mockReset();
  newsFindMany.mockReset();
  newsFindMany.mockResolvedValue([]);
  // A single, unambiguous US instrument so identity resolution succeeds.
  assetFindMany.mockResolvedValue([
    { symbol: "AAPL", name: "Apple Inc.", securityType: "Stock", market: { country: "US" } },
  ]);
  assetFindFirst.mockResolvedValue(null);
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

describe("fetchCapability — market_snapshot live fallback", () => {
  it("serves a live quote when the vault has NO row for the symbol", async () => {
    assetFindMany.mockResolvedValue([]); // outside the committed universe
    fetchQuoteWithFallback.mockResolvedValue({
      status: "ok",
      source: "yfinance",
      quote: { symbol: "NEWCO", price: 12.5, changePct: 0.4, volume: 100, marketCap: 1e9, market: "US", currency: "USD" },
    });
    const result = await fetchCapability("market_snapshot", { symbol: "NEWCO", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.served).toBe("live");
    expect((result.price as { price: number }).price).toBe(12.5);
    expect(result.observationSource).toBe("unknown");
  });

  it("serves a live quote when the vault row has no stored price", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "AAPL", name: "Apple Inc.", securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" }, price: null },
    ]);
    fetchQuoteWithFallback.mockResolvedValue({
      status: "ok",
      source: "yfinance",
      quote: { symbol: "AAPL", price: 240.1, changePct: 1.2, volume: 10, marketCap: 3e12, market: "US", currency: "USD" },
    });
    const result = await fetchCapability("market_snapshot", { symbol: "AAPL", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.served).toBe("live");
    expect((result.price as { price: number }).price).toBe(240.1);
  });

  it("still returns UNAVAILABLE when neither the vault nor a live provider answers", async () => {
    assetFindMany.mockResolvedValue([]);
    fetchQuoteWithFallback.mockResolvedValue({ status: "empty", error: "no quote", source: "yfinance" });
    const result = await fetchCapability("market_snapshot", { symbol: "ZZZZ", market: "US" });
    expect(result.status).toBe("UNAVAILABLE");
  });
});

describe("fetchCapability — price_history", () => {
  it("returns a real series from the batched bridge", async () => {
    fetchYahooBatchRaw.mockResolvedValue({ history: { "AAPL": [{ date: "2026-09-18", close: 1 }, { date: "2026-09-19", close: 2 }] } });
    const result = await fetchCapability("price_history", { symbol: "AAPL", period: "1mo" });
    expect(result.status).toBe("OK");
    expect(result.transport).toBe("yfinance-bridge");
    expect((result.series as unknown[]).length).toBe(2);
    // The bridge answered; the direct transport was never needed.
    expect(fetchYahooChartSeries).not.toHaveBeenCalled();
  });

  it("falls back to the direct chart transport when the bridge is off", async () => {
    fetchYahooBatchRaw.mockRejectedValue(new Error("python missing"));
    fetchYahooChartSeries.mockResolvedValue({
      bars: [{ date: "2026-09-18", close: 1 }, { date: "2026-09-19", close: 2 }],
      meta: { price: 2 },
    });
    const result = await fetchCapability("price_history", { symbol: "AAPL" });
    expect(result.status).toBe("OK");
    expect(result.transport).toBe("yahoo-chart");
    expect(result.provider).toBe("yfinance");
    expect(result.providerSymbol).toBe("AAPL");
    expect((result.series as unknown[]).length).toBe(2);
  });

  it("honours an explicit start/end window (bridge rows filtered, never full history)", async () => {
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
    const result = await fetchCapability("price_history", {
      symbol: "AAPL",
      start: "2025-12-01",
      end: "2025-12-31",
    });
    expect(result.status).toBe("OK");
    // A 31-day window picks a covering range — never "max" (the old behaviour
    // returned everything and the renderer truncated head+tail).
    expect(fetchYahooBatchRaw).toHaveBeenCalledWith(
      ["AAPL"], "US", "1d", "1mo", { start: "2025-12-01", end: "2025-12-31" },
    );
    const dates = (result.series as Array<{ date: string }>).map((r) => r.date);
    expect(dates).toEqual(["2025-12-10", "2025-12-31"]);
    expect(result.window).toEqual({ start: "2025-12-01", end: "2025-12-31" });
  });

  it("returns UNAVAILABLE when neither transport has a series", async () => {
    fetchYahooBatchRaw.mockRejectedValue(new Error("offline"));
    const result = await fetchCapability("price_history", { symbol: "AAPL" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(fetchYahooChartSeries).toHaveBeenCalled();
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
    searchWeb.mockResolvedValue({
      results: [{ title: "t", url: "https://x", snippet: "s", publishedAt: null }],
      diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "ok", normalizedStatus: "ok" }],
      provider: "duckduckgo-html",
    });
    const result = await fetchCapability("web_search", { query: "q" });
    expect(result.status).toBe("OK");
    expect((result.results as unknown[]).length).toBe(1);
    expect(result.provider).toBe("duckduckgo-html");
  });

  it("web_search reports zero_results as no_data, never a failure", async () => {
    searchWeb.mockResolvedValue({
      results: [],
      diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "zero_results", normalizedStatus: "ok" }],
      provider: "duckduckgo-html",
    });
    const result = await fetchCapability("web_search", { query: "q" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("no_data");
  });

  it("web_search reports a transport failure as source_failure with diagnostics", async () => {
    searchWeb.mockResolvedValue({
      results: [],
      diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "blocked", normalizedStatus: "failed", detail: "HTTP 202" }],
      provider: null,
    });
    const result = await fetchCapability("web_search", { query: "q" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("source_failure");
    expect((result.diagnostics as unknown[]).length).toBe(1);
  });

  it("web_fetch returns page text", async () => {
    fetchWebPageDetailed.mockResolvedValue({
      page: { url: "https://x", title: "t", text: "body", bytes: 4 },
      diagnostic: { capability: "web_fetch", provider: "safe-get", category: "ok", normalizedStatus: "ok" },
    });
    const result = await fetchCapability("web_fetch", { url: "https://x" });
    expect(result.status).toBe("OK");
    expect(result.text).toBe("body");
  });

  it("web_fetch reports the failure category when the page cannot be retrieved", async () => {
    fetchWebPageDetailed.mockResolvedValue({
      page: null,
      diagnostic: { capability: "web_fetch", provider: "safe-get", category: "content_type_rejected", normalizedStatus: "failed", detail: "unsupported content type" },
    });
    const result = await fetchCapability("web_fetch", { url: "https://x" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("no_data");
    expect((result.diagnostics as unknown[]).length).toBe(1);
  });
});

describe("fetchCapability — news (C2: no false negatives)", () => {
  it("falls through to web when the vault is empty and returns real items", async () => {
    newsFindMany.mockResolvedValue([]);
    searchWeb.mockResolvedValue({
      results: [{ title: "FFC news", url: "https://x.com/a", snippet: "s", publishedAt: null }],
      diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "ok", normalizedStatus: "ok" }],
      provider: "duckduckgo-html",
    });
    const result = await fetchCapability("news", { query: "Pakistan fertilizer" });
    expect(result.status).toBe("OK");
    expect(result.sourceKind).toBe("web");
    expect((result.items as unknown[]).length).toBe(1);
  });

  it("reports a source failure, never an empty result, when retrieval errors", async () => {
    newsFindMany.mockResolvedValue([]);
    searchWeb.mockRejectedValue(new Error("network down"));
    const result = await fetchCapability("news", { query: "anything" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("source_failure");
  });

  it("returns no_data (not a failure) when sources are reachable but empty", async () => {
    newsFindMany.mockResolvedValue([]);
    searchWeb.mockResolvedValue({
      results: [],
      diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "zero_results", normalizedStatus: "ok" }],
      provider: "duckduckgo-html",
    });
    const result = await fetchCapability("news", { query: "zzz" });
    expect(result.status).toBe("OK");
    expect(result.failureClass).toBe("no_data");
    expect((result.items as unknown[]).length).toBe(0);
  });
});

describe("fetchCapability � coverage (C1)", () => {
  it("returns the declared coverage registry", async () => {
    const result = await fetchCapability("coverage", {});
    expect(result.status).toBe("OK");
    expect((result.rows as unknown[]).length).toBeGreaterThan(20);
  });
});
