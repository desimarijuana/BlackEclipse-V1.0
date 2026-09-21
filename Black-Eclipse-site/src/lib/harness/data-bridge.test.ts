import { describe, it, expect, vi, beforeEach } from "vitest";

// The JDdS data bridge is the single market-data accessor the Python tools use.
// Prisma is mocked so the test never touches the real jdds.db.

const findFirst = vi.fn();
const newsFindMany = vi.fn();
const groupBy = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: { findFirst: (...a: unknown[]) => findFirst(...a) },
    newsItem: { findMany: (...a: unknown[]) => newsFindMany(...a) },
    sourceHealth: { groupBy: (...a: unknown[]) => groupBy(...a) },
  },
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  findFirst.mockReset();
  newsFindMany.mockReset();
  groupBy.mockReset();
});

describe("fetchCapability — market_snapshot", () => {
  it("returns OK with provenance and freshness", async () => {
    findFirst.mockResolvedValue({
      symbol: "AAPL",
      name: "Apple Inc.",
      sector: "Technology",
      industry: "Consumer Electronics",
      securityType: "Common Stock",
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
    });
    const result = await fetchCapability("market_snapshot", { symbol: "aapl" });
    expect(result.status).toBe("OK");
    expect(result.priceSource).toBe("scraper");
    expect(result.updatedAt).toBe("2026-09-20T12:00:00.000Z");
    expect((result.price as { price: number }).price).toBe(237.42);
  });

  it("returns UNAVAILABLE when the symbol is absent (never invents data)", async () => {
    findFirst.mockResolvedValue(null);
    const result = await fetchCapability("market_snapshot", { symbol: "ZZZZ" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result).not.toHaveProperty("price");
  });

  it("returns UNAVAILABLE when no symbol is supplied", async () => {
    const result = await fetchCapability("market_snapshot", {});
    expect(result.status).toBe("UNAVAILABLE");
    expect(findFirst).not.toHaveBeenCalled();
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

  it("source_health aggregates", async () => {
    groupBy.mockResolvedValue([
      { source: "http", market: "US", _sum: { successCount: 3, failCount: 1 }, _max: { lastStatus: "ok" } },
    ]);
    const result = await fetchCapability("source_health", {});
    expect(result.status).toBe("OK");
    expect((result.rows as Array<{ success: number }>)[0].success).toBe(3);
  });

  it("rejects an unknown capability", async () => {
    const result = await fetchCapability("nope" as never, {});
    expect(result.status).toBe("UNAVAILABLE");
  });
});
