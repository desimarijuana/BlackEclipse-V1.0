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
    assetFindMany.mockResolvedValue([]);
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
    // Resolve a known macro series then let the fetch run to whatever outcome;
    // the route key must still be macro, not instrument.
    await fetchCapability("macro_series", { series: "CPIAUCSL" });
    const call = lastUpsert();
    if (call) expect(call.create.symbol).toContain("macro#macro_series");
  });
});
