import { describe, it, expect, vi, beforeEach } from "vitest";

// The JDdS data bridge is the single market-data accessor the Python tools use.
// Prisma is mocked so the test never touches the real jdds.db.

const findFirst = vi.fn();
const assetFindMany = vi.fn();
const newsFindMany = vi.fn();
const groupBy = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findFirst: (...a: unknown[]) => findFirst(...a),
      findMany: (...a: unknown[]) => assetFindMany(...a),
    },
    newsItem: { findMany: (...a: unknown[]) => newsFindMany(...a) },
    sourceHealth: { groupBy: (...a: unknown[]) => groupBy(...a) },
  },
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  findFirst.mockReset();
  assetFindMany.mockReset();
  newsFindMany.mockReset();
  groupBy.mockReset();
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

  it("source_health aggregates recorded runs and declares uncovered sources", async () => {
    groupBy.mockResolvedValue([
      { source: "http", market: "US", symbol: "equity", _sum: { successCount: 3, failCount: 1 }, _max: { lastStatus: "ok", updatedAt: new Date() } },
    ]);
    const result = await fetchCapability("source_health", {});
    expect(result.status).toBe("OK");
    // Every declared target is present, so "no data" is distinguishable from
    // "no source"; the US equity target carries the recorded 3 successes.
    const rows = result.rows as Array<{ market: string; assetClass: string; success: number; health: string }>;
    expect(rows.length).toBeGreaterThan(1);
    const us = rows.find((r) => r.market === "US" && r.assetClass === "equity");
    expect(us?.success).toBe(3);
    // A declared target with no recorded runs reports `unknown`, not absent.
    expect(rows.some((r) => r.health === "unknown")).toBe(true);
  });

  it("rejects an unknown capability", async () => {
    const result = await fetchCapability("nope" as never, {});
    expect(result.status).toBe("UNAVAILABLE");
  });
});
