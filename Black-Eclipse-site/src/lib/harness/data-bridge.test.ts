import { describe, it, expect, vi, beforeEach } from "vitest";

// The JDdS data bridge is the single market-data accessor the Python tools use.
// Prisma is mocked so the test never touches the real jdds.db.

const findFirst = vi.fn();
const assetFindMany = vi.fn();
const assetGroupBy = vi.fn();
const marketFindMany = vi.fn();
const newsFindMany = vi.fn();
const groupBy = vi.fn();
const fundamentalsCacheFindUnique = vi.fn();
const fundamentalsGet = vi.fn();
const yahooIsConfigured = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findFirst: (...a: unknown[]) => findFirst(...a),
      findMany: (...a: unknown[]) => assetFindMany(...a),
      groupBy: (...a: unknown[]) => assetGroupBy(...a),
    },
    market: { findMany: (...a: unknown[]) => marketFindMany(...a) },
    newsItem: { findMany: (...a: unknown[]) => newsFindMany(...a) },
    sourceHealth: { groupBy: (...a: unknown[]) => groupBy(...a) },
    fundamentalsCache: { findUnique: (...a: unknown[]) => fundamentalsCacheFindUnique(...a) },
  },
}));
vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  // No network in the default suite; the matrix treats SEC as unavailable here.
  secAvailable: () => Promise.resolve(false),
  fetchSecCompanyFacts: () => Promise.resolve(null),
}));
vi.mock("@/lib/fundamentals/providers/yahoo", () => ({
  yahooFundamentalsProvider: { isConfigured: (...a: unknown[]) => yahooIsConfigured(...a), supports: () => true },
}));
vi.mock("@/lib/fundamentals", () => ({
  // The live statement fallback routes through the existing service.
  getFundamentals: (...a: unknown[]) => fundamentalsGet(...a),
}));
vi.mock("@/lib/provider-keys", () => ({
  resolveProviderKey: () => Promise.resolve(null),
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  findFirst.mockReset();
  assetFindMany.mockReset();
  assetGroupBy.mockReset();
  assetGroupBy.mockResolvedValue([]);
  marketFindMany.mockReset();
  marketFindMany.mockResolvedValue([]);
  newsFindMany.mockReset();
  groupBy.mockReset();
  fundamentalsCacheFindUnique.mockReset();
  fundamentalsCacheFindUnique.mockResolvedValue(null);
  fundamentalsGet.mockReset();
  fundamentalsGet.mockResolvedValue(null);
  yahooIsConfigured.mockReset();
  // Default the keyless multi-market vendor to UNAVAILABLE so capability tests
  // can assert the unconfigured state; the statements test sets its own mocks.
  yahooIsConfigured.mockResolvedValue(false);
});

describe("fetchCapability — market_snapshot", () => {
  it("returns OK with provenance and freshness", async () => {
    assetFindMany.mockResolvedValue([
      {
        symbol: "AAPL",
        name: "Apple Inc.",
        sector: "Technology",
        industry: "Consumer Electronics",
        securityType: "Common Stock",
        assetClass: "Equity",
        market: { country: "US", exchange: "NASDAQ" },
        price: {
          price: 237.42,
          changePct: 1.23,
          marketCap: null,
          volume: null,
          peRatio: null,
          source: "scraper",
          updatedAt: new Date("2026-09-20T12:00:00.000Z"),
        },
      },
    ]);
    const result = await fetchCapability("market_snapshot", { symbol: "aapl" });
    expect(result.status).toBe("OK");
    expect(result.priceSource).toBe("scraper");
    expect(result.updatedAt).toBe("2026-09-20T12:00:00.000Z");
    expect((result.price as { price: number }).price).toBe(237.42);
  });

  it("returns UNAVAILABLE when the symbol is absent (never invents data)", async () => {
    assetFindMany.mockResolvedValue([]);
    const result = await fetchCapability("market_snapshot", { symbol: "ZZZZ" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result).not.toHaveProperty("price");
  });

  it("returns UNAVAILABLE when no symbol is supplied", async () => {
    const result = await fetchCapability("market_snapshot", {});
    expect(result.status).toBe("UNAVAILABLE");
    expect(assetFindMany).not.toHaveBeenCalled();
  });
});

describe("fetchCapability — other capabilities", () => {
  it("news maps stored rows", async () => {
    newsFindMany.mockResolvedValue([
      { source: "Reuters", headline: "H", summary: "S", sentiment: "bullish", url: "u", timestamp: new Date() },
    ]);
    const result = await fetchCapability("news", { query: "oil" });
    expect(result.status).toBe("OK");
    expect((result.items as unknown[]).length).toBe(1);
  });

  it("source_health keys each route by provider × market × asset class × capability", async () => {
    groupBy.mockResolvedValue([
      { source: "yfinance", market: "US", symbol: "equity", _sum: { successCount: 3, failCount: 1 }, _max: { lastStatus: "ok", updatedAt: new Date() } },
    ]);
    // The full declared enumeration is opt-in now (Phase 2); the default shape
    // is a compact recorded head, so the declared-route assertions need
    // `includeDeclared: true`.
    const result = await fetchCapability("source_health", { includeDeclared: true });
    expect(result.status).toBe("OK");
    const rows = result.rows as Array<{ source: string; market: string; assetClass: string; capability: string; success: number; health: string }>;
    expect(rows.length).toBeGreaterThan(1);
    // The recorded route is keyed by ITS provider, not merged onto every source.
    const recorded = rows.find((r) => r.source === "yfinance" && r.market === "US" && r.assetClass === "equity");
    expect(recorded?.success).toBe(3);
    expect(recorded?.health).toBe("degraded");
    // A different provider's US-equity route must NOT inherit those counts.
    const jdds = rows.find((r) => r.source === "JDDS" && r.market === "US" && r.assetClass === "equity" && r.capability === "quote");
    expect(jdds?.success).toBe(0);
    expect(jdds?.health).toBe("unknown");
    // A declared target with no recorded runs reports `unknown`, not absent.
    expect(rows.some((r) => r.health === "unknown")).toBe(true);
    // Capabilities on the SAME source×market×assetClass are DISTINCT rows — a
    // working quote never shares a counter with an untested statement route.
    const jddsQuote = rows.find((r) => r.source === "JDDS" && r.assetClass === "equity" && r.capability === "quote");
    const jddsStmt = rows.find((r) => r.source === "JDDS" && r.assetClass === "equity" && r.capability === "financial_statements");
    expect(jddsStmt).toBeTruthy();
    expect(jddsStmt!.success).toBe(0);
    expect(jddsStmt!.health).toBe("unknown");
    void jddsQuote;
    // Rows are unique per (source, market, assetClass, capability) — no dupes.
    const keys = rows.map((r) => `${r.source}|${r.market}|${r.assetClass}|${r.capability}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("capability_matrix reports capability separately from market recognition", async () => {
    groupBy.mockResolvedValue([]);
    yahooIsConfigured.mockResolvedValue(false);
    const result = await fetchCapability("capability_matrix", {});
    expect(result.status).toBe("OK");
    const rows = result.rows as Array<{ market: string; quote: { level: string }; fundamentals: { level: string } }>;
    const tw = rows.find((r) => r.market === "TW");
    expect(tw).toBeTruthy();
    // With no statement provider usable, TW statements are unconfigured — NOT
    // advertised as working merely because quotes work.
    expect(tw!.fundamentals.level).toBe("unconfigured");
  });

  it("capability_matrix marks non-US statements configured when the keyless vendor is usable", async () => {
    groupBy.mockResolvedValue([]);
    yahooIsConfigured.mockResolvedValue(true);
    const result = await fetchCapability("capability_matrix", {});
    const rows = result.rows as Array<{ market: string; fundamentals: { level: string; via?: string } }>;
    const kr = rows.find((r) => r.market === "KR");
    expect(kr!.fundamentals.level).toBe("configured");
    expect(kr!.fundamentals.via).toMatch(/yfinance/i);
  });

  it("financial_statements falls back to the live provider when the vault is empty", async () => {
    assetFindMany.mockResolvedValue([
      { symbol: "005930", name: "Samsung Electronics", securityType: "Stock", assetClass: "Equity", market: { country: "KR", exchange: "KRX" } },
    ]);
    findFirst.mockResolvedValue(null);
    // No persisted statements for this market.
    fundamentalsCacheFindUnique.mockResolvedValue(null);
    fundamentalsGet.mockResolvedValue({
      symbol: "005930",
      market: "KR",
      currency: "KRW",
      primarySource: "yahoo",
      provenance: "LIVE",
      retrievedAt: "2026-09-23T00:00:00.000Z",
      periods: [{ endDate: "2024-12-31", revenue: 300870903000000, netIncome: 33621363000000 }],
    });
    const result = await fetchCapability("financial_statements", { symbol: "005930.KS", market: "KR" });
    expect(result.status).toBe("OK");
    expect(result.provider).toBe("yahoo");
    expect(result.currency).toBe("KRW");
    expect((result.periods as unknown[]).length).toBe(1);
    // The live service was consulted exactly because the vault had no rows.
    expect(fundamentalsGet).toHaveBeenCalledWith("005930", "KR", expect.anything());
  });

  it("rejects an unknown capability", async () => {
    const result = await fetchCapability("nope" as never, {});
    expect(result.status).toBe("UNAVAILABLE");
  });
});
