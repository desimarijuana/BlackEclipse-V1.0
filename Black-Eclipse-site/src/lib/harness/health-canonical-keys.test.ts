import { describe, it, expect, vi, beforeEach } from "vitest";

// P0-3 + P1-5 — canonical route keys and probe persistence.
//
// Before this change the ledger was fragmented: the same real route could be
// split by casing (`Equity` vs `equity`) or an unresolved `unknown`, and the
// research-health probe tested one provider while production recorded another
// (a working provider shown as failing). These tests pin the closed vocabulary,
// the alias folding, and the fact that a probe run and a production run of the
// same capability land on ONE row.

const sourceHealthUpsert = vi.fn();
const sourceHealthGroupBy = vi.fn();
const searchWeb = vi.fn();
const fetchWebPageDetailed = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    sourceHealth: {
      upsert: (...a: unknown[]) => sourceHealthUpsert(...a),
      groupBy: (...a: unknown[]) => sourceHealthGroupBy(...a),
    },
  },
}));
vi.mock("@/lib/web-research", () => ({
  searchWeb: (...a: unknown[]) => searchWeb(...a),
  fetchWebPageDetailed: (...a: unknown[]) => fetchWebPageDetailed(...a),
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
vi.mock("@/lib/scraper/fetchers", () => ({ fetchQuoteWithFallback: vi.fn() }));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({ fetchYahooBatchRaw: vi.fn() }));
vi.mock("@/lib/economics/sources", () => ({ getSource: () => undefined }));

import { fetchCapability } from "./data-bridge";
import { canonicalMarket, canonicalAssetClass, canonicalSource } from "./health-key";

const okDiag = (capability: string, provider: string) => ({
  capability,
  provider,
  tier: "unknown",
  normalizedStatus: "ok",
  category: "ok",
});

beforeEach(() => {
  vi.clearAllMocks();
  sourceHealthUpsert.mockResolvedValue({});
  sourceHealthGroupBy.mockResolvedValue([]);
  searchWeb.mockResolvedValue({
    results: [{ title: "x", url: "https://example.com", snippet: "s" }],
    provider: "duckduckgo-html",
    diagnostics: [okDiag("web_search", "duckduckgo-html")],
  });
  fetchWebPageDetailed.mockResolvedValue({
    status: "ok",
    page: { url: "https://example.com", title: "t", text: "body", bytes: 4 },
    diagnostic: okDiag("web_fetch", "safe-get"),
  });
});

function upsertsFor(symbol: string) {
  return sourceHealthUpsert.mock.calls.map((c) => c[0]).find((u) => u.create.symbol === symbol);
}

describe("canonical route-key vocabulary (P1-5)", () => {
  it("uppercases known markets and wildcards the rest", () => {
    expect(canonicalMarket("us")).toBe("US");
    expect(canonicalMarket("pk")).toBe("PK");
    expect(canonicalMarket("unknown")).toBe("*");
    expect(canonicalMarket("")).toBe("*");
  });

  it("lowercases known asset classes and maps aliases", () => {
    expect(canonicalAssetClass("Equity")).toBe("equity");
    expect(canonicalAssetClass("ETF")).toBe("etf");
    expect(canonicalAssetClass("Stock")).toBe("equity");
    expect(canonicalAssetClass("unknown")).toBe("*");
    expect(canonicalAssetClass(null)).toBe("*");
    // `macro` is a real synthetic class, never folded to the wildcard.
    expect(canonicalAssetClass("macro")).toBe("macro");
  });

  it("folds provider/transport variants onto one source id, never inventing 'unknown'", () => {
    expect(canonicalSource("safe-get")).toBe("WEB");
    expect(canonicalSource("duckduckgo-html")).toBe("WEB");
    expect(canonicalSource("custom-search")).toBe("WEB");
    expect(canonicalSource("sec-xbrl")).toBe("SEC");
    expect(canonicalSource("yfinance")).toBe("yfinance");
  });
});

describe("research-health probes write to the same ledger as production (P0-3)", () => {
  it("persists each probe under the canonical, instrument-less route key", async () => {
    await fetchCapability("research_health", {});
    expect(upsertsFor("*#web_search")?.create.source).toBe("WEB");
    expect(upsertsFor("*#web_search")?.create.market).toBe("*");
    expect(upsertsFor("*#web_fetch")?.create.source).toBe("WEB");
    // The SEC reachability probe is recorded as the SEC filings route, not WEB.
    expect(upsertsFor("*#sec_filings")?.create.source).toBe("SEC");
  });
});

describe("source-health reads fold legacy/unnormalised rows (P1-5)", () => {
  it("folds a mixed-case market + asset class onto the canonical row", async () => {
    sourceHealthGroupBy.mockResolvedValue([
      {
        source: "LIVE_STRUCTURED",
        market: "us",
        symbol: "Equity#live_quote",
        _sum: { successCount: 5, failCount: 0 },
        _max: { lastStatus: "ok", updatedAt: new Date() },
      },
    ]);
    const result = await fetchCapability("source_health", {});
    const row = (result.rows as Array<Record<string, unknown>>).find(
      (r) => r.source === "LIVE_STRUCTURED" && r.capability === "live_quote" && r.assetClass === "equity"
    );
    expect(row).toBeTruthy();
    expect(row?.market).toBe("US");
    expect(row?.success).toBe(5);
  });
});
