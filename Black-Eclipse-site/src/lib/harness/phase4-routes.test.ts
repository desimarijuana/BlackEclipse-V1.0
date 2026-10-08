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

describe("Phase 4.3 — declared secondary tier", () => {
  it("PK carries the secondary tier and is labelled", () => {
    const matrix = buildCapabilityMatrix();
    const pk = matrix.find((m) => m.market === "PK")!;
    expect(pk.quote.tier).toBe("secondary");
  });
});
