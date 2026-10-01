import { describe, it, expect, vi, beforeEach } from "vitest";

// Harness closeout Phase 2 — the sourceHealth summary partition. Before this,
// sourceHealth() emitted EVERY declared route (~1,196 rows / ~158k chars) BEFORE
// any recorded row, so the bounded (24k) tool text only ever showed
// "unknown — 0 ok / 0 fail" rows and a working system looked dead. The default
// is now a compact summary head; the full declared enumeration is opt-in.

const sourceHealthGroupBy = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    sourceHealth: {
      groupBy: (...a: unknown[]) => sourceHealthGroupBy(...a),
    },
  },
}));
vi.mock("@/lib/scraper/fetchers", () => ({ fetchQuoteWithFallback: vi.fn() }));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({ fetchYahooBatchRaw: vi.fn() }));
vi.mock("@/lib/web-research", () => ({
  searchWeb: vi.fn().mockResolvedValue({ results: [], provider: "x", diagnostics: [] }),
  fetchWebPageDetailed: vi.fn(),
}));
vi.mock("@/lib/web-search", () => ({
  resolveSearchProviders: () => [],
  CustomJsonSearchProvider: class {},
}));
vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: () => Promise.resolve(null) }));
vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  secAvailable: () => Promise.resolve(false),
  fetchSecCompanyFacts: () => Promise.resolve(null),
}));
vi.mock("@/lib/fundamentals/providers/yahoo", () => ({
  yahooFundamentalsProvider: { isConfigured: () => true, supports: () => true },
}));
vi.mock("@/lib/fundamentals", () => ({ getFundamentals: vi.fn() }));
vi.mock("@/lib/harness/route-probe", () => ({ runRouteHealthProbe: vi.fn() }));

import { fetchCapability } from "./data-bridge";

const NOW = new Date("2026-09-30T00:00:00.000Z");

beforeEach(() => {
  vi.clearAllMocks();
});

describe("sourceHealth summary head", () => {
  it("returns a compact summary + recorded rows, withholding the declared list", async () => {
    // Two recorded live routes (one healthy, one failing).
    sourceHealthGroupBy.mockResolvedValue([
      {
        source: "LIVE_STRUCTURED", market: "US", symbol: "equity#live_quote",
        _sum: { successCount: 10, failCount: 0 },
        _max: { lastStatus: "ok", updatedAt: NOW, lastSuccessAt: NOW, lastFailureAt: null },
      },
      {
        source: "LIVE_STRUCTURED", market: "PK", symbol: "equity#live_quote",
        _sum: { successCount: 0, failCount: 3 },
        _max: { lastStatus: "fail", updatedAt: NOW, lastSuccessAt: null, lastFailureAt: NOW },
      },
    ]);

    const result = await fetchCapability("source_health", {});
    const summary = result.summary as Record<string, unknown>;
    const rows = result.rows as Array<Record<string, unknown>>;

    expect(result.status).toBe("OK");
    // The recorded rows are present and name their true counters.
    const us = rows.find((r) => r.market === "US");
    expect(us).toBeTruthy();
    expect(us!.success).toBe(10);
    expect(us!.health).toBe("healthy");
    expect(us!.lastSuccessAt).toBe(NOW.toISOString());
    const pk = rows.find((r) => r.market === "PK");
    expect(pk!.fail).toBe(3);
    expect(pk!.health).toBe("failing");
    expect(pk!.lastFailureAt).toBe(NOW.toISOString());

    // The declared-but-unrun list is WITHHELD (counted, not enumerated).
    expect(typeof result.withheld).toBe("number");
    expect(result.withheld as number).toBeGreaterThan(0);
    // Every returned row is a recorded row (has attempts), never a declared-only.
    expect(rows.every((r) => (r.total as number) > 0)).toBe(true);

    expect(summary.recordedRoutes).toBe(2);
    expect((summary.marketsWithAttempts as string[]).sort()).toEqual(["PK", "US"]);
  });

  it("recordedOnly returns only recorded rows and no declared rows", async () => {
    sourceHealthGroupBy.mockResolvedValue([
      {
        source: "LIVE_STRUCTURED", market: "US", symbol: "equity#live_quote",
        _sum: { successCount: 1, failCount: 0 },
        _max: { lastStatus: "ok", updatedAt: NOW, lastSuccessAt: NOW, lastFailureAt: null },
      },
    ]);
    const result = await fetchCapability("source_health", { recordedOnly: true });
    const rows = result.rows as Array<Record<string, unknown>>;
    expect(rows).toHaveLength(1);
    expect(rows[0].market).toBe("US");
    expect(result.withheld).toBe(0);
  });

  it("includeDeclared enumerates the declared universe as `unknown`", async () => {
    sourceHealthGroupBy.mockResolvedValue([]);
    const result = await fetchCapability("source_health", { includeDeclared: true });
    const rows = result.rows as Array<Record<string, unknown>>;
    // A sparse ledger with includeDeclared still returns a large declared list,
    // every one of which is `unknown` (zero attempts), never healthy.
    expect(rows.length).toBeGreaterThan(100);
    expect(rows.every((r) => r.health === "unknown")).toBe(true);
    expect(result.withheld).toBe(0);
  });

  it("an empty ledger with the default shape is no_data, not a false healthy", async () => {
    sourceHealthGroupBy.mockResolvedValue([]);
    const result = await fetchCapability("source_health", {});
    expect(result.status).toBe("OK");
    expect(result.summary).not.toBeUndefined();
    const rows = result.rows as unknown[];
    expect(rows).toHaveLength(0);
  });
});
