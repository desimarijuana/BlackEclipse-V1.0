import { describe, it, expect, vi, beforeEach } from "vitest";

// Harness closeout Phase 4 — data-route gaps.

const assetFindMany = vi.fn();
const fundamentalsCacheFindUnique = vi.fn();
const sourceHealthUpsert = vi.fn();
const sourceHealthGroupBy = vi.fn();
const getFundamentals = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: { findMany: (...a: unknown[]) => assetFindMany(...a), findFirst: vi.fn() },
    fundamentalsCache: { findUnique: (...a: unknown[]) => fundamentalsCacheFindUnique(...a) },
    sourceHealth: {
      upsert: (...a: unknown[]) => sourceHealthUpsert(...a),
      groupBy: (...a: unknown[]) => sourceHealthGroupBy(...a),
    },
  },
}));
vi.mock("@/lib/fundamentals", () => ({ getFundamentals: (...a: unknown[]) => getFundamentals(...a) }));
vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  secAvailable: () => Promise.resolve(false),
  fetchSecCompanyFacts: () => Promise.resolve(null),
}));
vi.mock("@/lib/fundamentals/providers/yahoo", () => ({
  yahooFundamentalsProvider: { isConfigured: () => true, supports: () => true },
}));
vi.mock("@/lib/scraper/fetchers", () => ({ fetchQuoteWithFallback: vi.fn() }));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({ fetchYahooBatchRaw: vi.fn() }));
vi.mock("@/lib/web-research", () => ({
  searchWeb: vi.fn().mockResolvedValue([]),
  fetchWebPageDetailed: vi.fn(),
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

import { fetchCapability } from "./data-bridge";
import { buildCapabilityMatrix } from "./capability";

beforeEach(() => {
  vi.clearAllMocks();
  assetFindMany.mockResolvedValue([]);
  fundamentalsCacheFindUnique.mockResolvedValue(null);
  sourceHealthGroupBy.mockResolvedValue([]);
  sourceHealthUpsert.mockResolvedValue({});
});

describe("Phase 4.4 — statements resolve through the provider chain, vault as cache", () => {
  it("a statement request for a market with NO vault row returns periods, not a vault identity failure", async () => {
    // No vault rows at all, but the market is known/covered (US).
    assetFindMany.mockResolvedValue([]);
    getFundamentals.mockResolvedValue({
      symbol: "XYZ", market: "US", currency: "USD",
      primarySource: "yfinance",
      retrievedAt: "2026-09-30T00:00:00Z",
      provenance: "live",
      periods: [{ period: "2025", revenue: 100 }],
    });
    const result = await fetchCapability("financial_statements", { symbol: "XYZ", market: "US" });
    expect(result.status).toBe("OK");
    expect((result.periods as unknown[]).length).toBe(1);
  });

  it("returns no_data (never a vault identity failure) when the provider chain has nothing", async () => {
    assetFindMany.mockResolvedValue([]);
    getFundamentals.mockResolvedValue({ symbol: "XYZ", market: "US", currency: "USD", periods: [] });
    const result = await fetchCapability("financial_statements", { symbol: "XYZ", market: "US" });
    // The identity resolved via the fallback, so the provider chain answered with
    // an honest no_data — NOT a not_found identity failure.
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("no_data");
  });

  it("an unknown venue still fails honestly (no fabricated identity)", async () => {
    assetFindMany.mockResolvedValue([]);
    const result = await fetchCapability("financial_statements", { symbol: "ZZZ", market: "NOWHERE" });
    expect(result.status).not.toBe("OK");
    expect(result.failureClass).not.toBe("no_data");
  });
});

describe("stale statements cache (VAULT-1)", () => {
  const cachedRow = (fetchedAt: Date) => ({
    symbol: "AAPL",
    market: "US",
    primarySource: "sec-edgar",
    fetchedAt,
    payload: JSON.stringify({
      cacheVersion: 2,
      primarySource: "sec-edgar",
      periods: [{ period: "2026", endDate: new Date().toISOString().slice(0, 10), revenue: 1 }],
    }),
  });

  it("serves a FRESH cached snapshot with its age and no provider call", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "AAPL", name: "Apple Inc.", securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" }, price: null },
    ]);
    fundamentalsCacheFindUnique.mockResolvedValue(cachedRow(new Date(Date.now() - 3600_000)));
    const result = await fetchCapability("financial_statements", { symbol: "AAPL", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.provenance).toBe("CACHED");
    expect(result.cacheAgeDays).toBe(0);
    expect(getFundamentals).not.toHaveBeenCalled();
  });

  it("refreshes a snapshot older than the cadence instead of serving FY2018/19 as current", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "AAPL", name: "Apple Inc.", securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" }, price: null },
    ]);
    fundamentalsCacheFindUnique.mockResolvedValue(cachedRow(new Date(Date.now() - 60 * 24 * 3600_000)));
    getFundamentals.mockResolvedValue({
      symbol: "AAPL", market: "US", currency: "USD", primarySource: "yahoo",
      retrievedAt: "2026-10-13T00:00:00Z", provenance: "live",
      periods: [{ period: "2025", revenue: 42 }],
    });
    const result = await fetchCapability("financial_statements", { symbol: "AAPL", market: "US" });
    expect(result.status).toBe("OK");
    expect(getFundamentals).toHaveBeenCalledWith("AAPL", "US", { force: true });
    expect(result.provenance).toBe("live");
    expect((result.periods as Array<{ period: string }>)[0].period).toBe("2025");
  });

  it("keeps the stale snapshot when the refresh fails, labelled with its age", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "AAPL", name: "Apple Inc.", securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" }, price: null },
    ]);
    fundamentalsCacheFindUnique.mockResolvedValue(cachedRow(new Date(Date.now() - 60 * 24 * 3600_000)));
    getFundamentals.mockRejectedValue(new Error("providers offline"));
    const result = await fetchCapability("financial_statements", { symbol: "AAPL", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.provenance).toBe("CACHED");
    expect(result.stale).toBe(true);
    expect(result.cacheAgeDays).toBe(60);
    expect((result.periods as unknown[]).length).toBe(1);
  });
});

describe("fundamentals valuation provenance (DATA-1)", () => {
  it("labels saved ratios JDDS with their as-of", async () => {
    assetFindMany.mockResolvedValue([
      {
        symbol: "AAPL", name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics",
        securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" },
        price: { price: 240, peRatio: 31.2, forwardPE: 28.4, source: "yfinance", updatedAt: new Date("2026-10-13T12:00:00Z") },
      },
    ]);
    const result = await fetchCapability("fundamentals", { symbol: "AAPL", market: "US" });
    expect(result.status).toBe("OK");
    const valuation = result.valuation as { peRatio: number; provenance: string; asOf: string };
    expect(valuation.provenance).toBe("JDDS");
    expect(valuation.peRatio).toBe(31.2);
    expect(valuation.asOf).toContain("2026-10-13");
  });

  it("serves LIVE ratios with refresh=true", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", securityType: "Stock", assetClass: "Equity", market: { country: "US", exchange: "NASDAQ" }, price: null },
    ]);
    getFundamentals.mockResolvedValue({
      symbol: "AAPL", market: "US", currency: "USD", retrievedAt: "2026-10-13T18:00:00Z",
      company: { name: "Apple Inc.", sector: "Technology", industry: "CE", country: "US", exchange: "NASDAQ" },
      metrics: [
        { key: "pe", value: 30.1, source: "yahoo" },
        { key: "forwardPE", value: 27.9, source: "yahoo" },
      ],
    });
    const result = await fetchCapability("fundamentals", { symbol: "AAPL", market: "US", refresh: true });
    expect(result.status).toBe("OK");
    const valuation = result.valuation as { peRatio: number; forwardPE: number; provenance: string; source: string };
    expect(valuation).toMatchObject({ peRatio: 30.1, forwardPE: 27.9, provenance: "LIVE", source: "yahoo" });
  });
});

describe("Phase 4.3 — declared secondary tier", () => {
  it("PK carries the secondary tier and is labelled", () => {
    const matrix = buildCapabilityMatrix();
    const pk = matrix.find((m) => m.market === "PK")!;
    expect(pk.quote.tier).toBe("secondary");
  });
});
