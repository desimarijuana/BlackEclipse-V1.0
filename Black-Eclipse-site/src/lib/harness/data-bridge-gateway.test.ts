import { describe, it, expect, vi, beforeEach } from "vitest";

// The Financial Data Gateway's crypto bridge capability. The crypto connector
// transport is mocked so the test asserts the bridge's own mapping (pair
// resolution, identity, honest failure), not a provider.

const fetchCryptoQuote = vi.fn();
const assetFindMany = vi.fn();
const assetFindFirst = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    asset: {
      findMany: (...a: unknown[]) => assetFindMany(...a),
      findFirst: (...a: unknown[]) => assetFindFirst(...a),
    },
    newsItem: { findMany: vi.fn().mockResolvedValue([]) },
  },
}));
vi.mock("@/lib/scraper/fetchers/crypto", () => ({
  fetchCryptoQuote: (...a: unknown[]) => fetchCryptoQuote(...a),
}));
vi.mock("@/lib/scraper/fetchers", () => ({ fetchQuoteWithFallback: vi.fn() }));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({ fetchYahooBatchRaw: vi.fn() }));
vi.mock("@/lib/web-research", () => ({
  webSearch: vi.fn(),
  fetchWebPage: vi.fn(),
  searchWeb: vi.fn(),
  fetchWebPageDetailed: vi.fn(),
}));
vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: vi.fn().mockResolvedValue(null) }));

import { fetchCapability } from "./data-bridge";

beforeEach(() => {
  fetchCryptoQuote.mockReset();
  assetFindMany.mockReset();
  assetFindFirst.mockReset();
  assetFindMany.mockResolvedValue([]);
  assetFindFirst.mockResolvedValue(null);
});

describe("fetchCapability — crypto_market_data", () => {
  it("resolves a base/quote pair and returns identity", async () => {
    fetchCryptoQuote.mockResolvedValue({
      status: "ok",
      source: "crypto",
      quote: { symbol: "BTC", price: 64000, changePct: 2.1, volume: 1000 },
    });
    const result = await fetchCapability("crypto_market_data", { symbol: "BTC-USD" });
    expect(result.status).toBe("OK");
    expect(result.base).toBe("BTC");
    expect(result.quote).toBe("USD");
    expect(result.pair).toBe("BTC-USD");
    expect(result.assetClass).toBe("crypto");
    expect(fetchCryptoQuote).toHaveBeenCalledWith("BTC");
  });

  it("refuses a non-crypto identifier (never prices an equity as crypto)", async () => {
    const result = await fetchCapability("crypto_market_data", { symbol: "AAPL" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(fetchCryptoQuote).not.toHaveBeenCalled();
  });

  it("accepts a BARE base symbol (BTC, SOL) and defaults the quote to USD", async () => {
    fetchCryptoQuote.mockResolvedValue({
      status: "ok",
      source: "crypto",
      quote: { symbol: "SOL", price: 150, changePct: 1, volume: 2000, volumeBase: 12, volumeQuote: 2000 },
    });
    const result = await fetchCapability("crypto_market_data", { symbol: "SOL" });
    expect(result.status).toBe("OK");
    expect(result.pair).toBe("SOL-USD");
    // Both volumes are returned, explicitly labelled.
    expect(result.volume).toBe(2000);
    expect(result.volumeBase).toBe(12);
  });

  it("returns UNAVAILABLE honestly when the provider fails", async () => {
    fetchCryptoQuote.mockResolvedValue({ status: "network_error", error: "down", source: "crypto" });
    const result = await fetchCapability("crypto_market_data", { symbol: "ETH-USD" });
    expect(result.status).toBe("UNAVAILABLE");
    expect(result).not.toHaveProperty("price");
  });
});

describe("fetchCapability — provider_key_status", () => {
  it("reports credential presence only", async () => {
    const result = await fetchCapability("provider_key_status", { envVar: "POLYGON_API_KEY" });
    expect(result.status).toBe("OK");
    expect(result.configured).toBe(false);
    expect(result).not.toHaveProperty("value");
  });
});
