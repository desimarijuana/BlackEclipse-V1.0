import { describe, it, expect, vi, beforeEach } from "vitest";

// Phase 6: the SEC direct-filings route (independent of the JDdS vault) and the
// research health probe. The SEC adapter and the vault identity lookup are
// mocked, so the tests assert the bridge's own mapping + identity gating.

const assetFindMany = vi.fn();
const assetFindFirst = vi.fn();
const fetchSecCompanyFacts = vi.fn();
const resolveProviderKey = vi.fn();
const searchWeb = vi.fn();
const fetchWebPageDetailed = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findMany: (...a: unknown[]) => assetFindMany(...a),
      findFirst: (...a: unknown[]) => assetFindFirst(...a),
    },
  },
}));
vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  fetchSecCompanyFacts: (...a: unknown[]) => fetchSecCompanyFacts(...a),
}));
vi.mock("@/lib/provider-keys", () => ({
  resolveProviderKey: (...a: unknown[]) => resolveProviderKey(...a),
}));
vi.mock("@/lib/web-research", () => ({
  searchWeb: (...a: unknown[]) => searchWeb(...a),
  fetchWebPageDetailed: (...a: unknown[]) => fetchWebPageDetailed(...a),
}));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  assetFindMany.mockReset();
  assetFindFirst.mockReset();
  fetchSecCompanyFacts.mockReset();
  resolveProviderKey.mockReset();
  resolveProviderKey.mockResolvedValue(null);
  searchWeb.mockReset();
  fetchWebPageDetailed.mockReset();
  searchWeb.mockResolvedValue({
    results: [{ title: "t", url: "https://sec.gov/x", snippet: "s", publishedAt: null }],
    diagnostics: [{ capability: "web_search", provider: "duckduckgo-html", category: "ok", normalizedStatus: "ok" }],
    provider: "duckduckgo-html",
  });
  fetchWebPageDetailed.mockResolvedValue({
    page: { url: "https://sec.gov/x", title: "t", text: "body", bytes: 4 },
    diagnostic: { capability: "web_fetch", provider: "safe-get", category: "ok", normalizedStatus: "ok" },
  });
  // One unambiguous US instrument so the shared identity gate succeeds.
  assetFindMany.mockResolvedValue([
    { symbol: "NVDA", name: "NVIDIA Corporation", securityType: "Stock", market: { country: "US" } },
  ]);
  assetFindFirst.mockResolvedValue(null);
});

describe("fetchCapability — sec_filings", () => {
  it("returns SEC statement periods with primary provenance", async () => {
    fetchSecCompanyFacts.mockResolvedValue({
      provider: "sec-edgar",
      symbol: "NVDA",
      currency: "USD",
      retrievedAt: "2026-09-23T00:00:00.000Z",
      company: { name: "NVIDIA Corporation" },
      periods: [{ endDate: "2025-01-26", revenue: 130497000000, netIncome: 72880000000, form: "10-K", filed: "2026-02-25" }],
    });
    const result = await fetchCapability("sec_filings", { symbol: "NVDA", market: "US" });
    expect(result.status).toBe("OK");
    expect(result.provider).toBe("sec-edgar");
    expect((result.periods as unknown[]).length).toBe(1);
    expect(result.instrumentId).toBe("US:NVDA");
  });

  it("is not_covered for a non-US market", async () => {
    const result = await fetchCapability("sec_filings", { symbol: "NVDA", market: "JP" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("not_covered");
    expect(fetchSecCompanyFacts).not.toHaveBeenCalled();
  });

  it("goes through the shared identity gate (ambiguous ticker is refused)", async () => {
    // Two markets for one ticker, no qualifier → AMBIGUOUS, no SEC call.
    assetFindMany.mockResolvedValue([
      { symbol: "FFC", name: "US Fund", securityType: "Fund", market: { country: "US" } },
      { symbol: "FFC", name: "Fauji", securityType: "Stock", market: { country: "PK" } },
    ]);
    const result = await fetchCapability("sec_filings", { symbol: "FFC" });
    expect(result.status).toBe("AMBIGUOUS");
    expect(fetchSecCompanyFacts).not.toHaveBeenCalled();
  });

  it("reports no_data when SEC has no periods", async () => {
    fetchSecCompanyFacts.mockResolvedValue({ provider: "sec-edgar", symbol: "NVDA", currency: "USD", periods: [] });
    const result = await fetchCapability("sec_filings", { symbol: "NVDA", market: "US" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("no_data");
  });

  it("reports a source_failure when the adapter throws", async () => {
    fetchSecCompanyFacts.mockRejectedValue(new Error("network down"));
    const result = await fetchCapability("sec_filings", { symbol: "NVDA", market: "US" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.failureClass).toBe("source_failure");
  });
});

describe("fetchCapability — research_health", () => {
  it("returns per-capability health rows", async () => {
    const result = await fetchCapability("research_health", {});
    expect(result.status).toBe("OK");
    const rows = result.rows as Array<{ provider: string; capability: string; ok: boolean }>;
    expect(rows.length).toBeGreaterThan(0);
    // The SEC probe row is present and names its capability.
    expect(rows.some((r) => r.provider === "sec-xbrl")).toBe(true);
  });
});
