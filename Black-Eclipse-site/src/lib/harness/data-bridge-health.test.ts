import { describe, it, expect, vi, beforeEach } from "vitest";

// Issue 2 — health instrumentation coverage. Before this change, ONLY
// `liveQuote` recorded health, so a US-equity quote served via
// `market_snapshot` (and every fundamentals/filings/news route) never landed in
// the ledger. These tests prove one boundary seam records every data-fetching
// capability with a canonical route key, and that introspection routes do not
// record themselves.

const assetFindFirst = vi.fn();
const assetFindMany = vi.fn();
const sourceHealthUpsert = vi.fn();
const sourceHealthGroupBy = vi.fn();
const fundamentalsCacheFindUnique = vi.fn();
const newsFindMany = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findFirst: (...a: unknown[]) => assetFindFirst(...a),
      findMany: (...a: unknown[]) => assetFindMany(...a),
    },
    sourceHealth: {
      upsert: (...a: unknown[]) => sourceHealthUpsert(...a),
      groupBy: (...a: unknown[]) => sourceHealthGroupBy(...a),
    },
    fundamentalsCache: { findUnique: (...a: unknown[]) => fundamentalsCacheFindUnique(...a) },
    newsItem: { findMany: (...a: unknown[]) => newsFindMany(...a) },
  },
}));
vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  secAvailable: () => Promise.resolve(false),
  fetchSecCompanyFacts: () => Promise.resolve(null),
}));
vi.mock("@/lib/fundamentals/providers/yahoo", () => ({
  yahooFundamentalsProvider: { isConfigured: () => true, supports: () => true },
}));
vi.mock("@/lib/fundamentals", () => ({ getFundamentals: vi.fn() }));
vi.mock("@/lib/web-research", () => ({
  searchWeb: vi.fn().mockResolvedValue([]),
  fetchWebPageDetailed: vi.fn().mockResolvedValue({ status: "error" }),
}));
vi.mock("@/lib/web-search", () => ({
  resolveSearchProviders: () => [],
  CustomJsonSearchProvider: class {},
  resolveSearchApiConfig: () => null,
  buildPresetSearchProvider: () => null,
  firstConfiguredPreset: () => null,
  SEARCH_PROVIDER_PRESETS: [],
}));
vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: () => Promise.resolve(null) }));
vi.mock("@/lib/scraper/fetchers", () => ({
  fetchQuoteWithFallback: vi.fn().mockResolvedValue({
    status: "ok", source: "scraper", quote: { symbol: "AAPL", price: 100, changePct: 1, market: "US", currency: "USD" },
  }),
}));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: vi.fn().mockResolvedValue({ quotes: {}, history: {} }),
}));
// The macro source must be hermetic. Without this mock the `macro_series` case
// falls through to the REAL `macroSeries()` → `source.fetch()`, which makes an
// uncontrolled network request; under parallel load that wall-clock call could
// exceed the 5 s test timeout (the flake this file hit). A deterministic stub
// makes the route-identity assertion the only thing under test.
vi.mock("@/lib/economics/sources", () => ({
  getSource: (id: string) =>
    id === "fred-analytics"
      ? {
          id,
          label: "FRED Analytics",
          controls: [{ name: "seriesId", defaultValue: "CPIAUCSL" }],
          fetch: async () => [{ date: "2026-08-01", value: "3.1" }],
        }
      : undefined,
}));

import { fetchCapability } from "./data-bridge";

function lastUpsert() {
  const calls = sourceHealthUpsert.mock.calls;
  return calls.length ? calls[calls.length - 1][0] : null;
}

beforeEach(() => {
  vi.clearAllMocks();
  // A resolved US equity so market_snapshot succeeds. The vault resolver reads
  // through `asset.findMany`.
  assetFindMany.mockResolvedValue([
    {
      symbol: "AAPL", name: "Apple", sector: null, industry: null, securityType: "Common Stock",
      assetClass: "equity", market: { country: "US", exchange: "NASDAQ" },
      price: { price: 100, changePct: 1, marketCap: null, volume: null, peRatio: null, source: "scraper", updatedAt: new Date() },
    },
  ]);
  assetFindFirst.mockResolvedValue(null);
  fundamentalsCacheFindUnique.mockResolvedValue(null);
  newsFindMany.mockResolvedValue([]);
  sourceHealthGroupBy.mockResolvedValue([]);
  sourceHealthUpsert.mockResolvedValue({});
});

describe("one health seam records every data capability", () => {
  it("records a US-equity quote served via market_snapshot (was never recorded)", async () => {
    await fetchCapability("market_snapshot", { symbol: "AAPL", market: "US" });
    const call = lastUpsert();
    expect(call).toBeTruthy();
    // Canonical key: (source × market × assetClass) with capability encoded in `symbol`.
    expect(call.create.market).toBe("US");
    expect(call.create.symbol).toBe("equity#live_quote");
    expect(call.create.successCount).toBe(1);
  });

  it("records a failing route as a failure, not a silent skip", async () => {
    // A vault miss now falls back to a live quote (multi-source). For a symbol
    // NEITHER source can answer, both must fail so the route is recorded as a
    // failure. The default mock returns a quote; make the live route empty.
    assetFindMany.mockResolvedValue([]);
    const { fetchQuoteWithFallback } = await import("@/lib/scraper/fetchers");
    (fetchQuoteWithFallback as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: "empty", source: "scraper", error: "no quote",
    });
    await fetchCapability("market_snapshot", { symbol: "ZZZZ", market: "US" });
    const call = lastUpsert();
    expect(call).toBeTruthy();
    expect(call.create.failCount).toBe(1);
    expect(call.create.lastStatus).toBe("fail");
  });

  it("does not record the introspection/reporting routes themselves", async () => {
    await fetchCapability("source_health", {});
    await fetchCapability("coverage", {});
    await fetchCapability("capability_matrix", {});
    expect(sourceHealthUpsert).not.toHaveBeenCalled();
  });

  it("attributes macro series to the macro asset class", async () => {
    // The macro source is stubbed deterministically (see the mock above), so a
    // resolved series always records a route key — no wall-clock network call.
    await fetchCapability("macro_series", { series: "CPIAUCSL" });
    const call = lastUpsert();
    expect(call).toBeTruthy();
    expect(call.create.symbol).toContain("macro#macro_series");
    expect(call.create.market).toBe("US");
  });
});
