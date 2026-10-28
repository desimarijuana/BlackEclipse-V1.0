import { describe, expect, it, vi, beforeEach } from "vitest";

// The dispatcher is exercised with mocked adapters: no network.

vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: vi.fn(),
}));
vi.mock("@/lib/scraper/yahoo-chart", () => ({ fetchYahooChartSeries: vi.fn() }));
vi.mock("@/lib/connectors/security", () => ({ safeGet: vi.fn(), safePost: vi.fn() }));
vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: vi.fn(async () => null) }));

import { fetchYahooBatchRaw } from "@/lib/scraper/fetchers/yfinance";
import { safeGet } from "@/lib/connectors/security";
import { fetchMarketData, listMarketProviders } from "@/lib/harness/market/bridge";

const mockedYahoo = vi.mocked(fetchYahooBatchRaw);
const mockedSafeGet = vi.mocked(safeGet);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("market adapter registry", () => {
  it("advertises the implemented providers and their capabilities", () => {
    const providers = listMarketProviders();
    const ids = providers.map((p) => p.id);
    expect(ids).toContain("yahoo");
    expect(ids).toContain("binance");
    expect(ids).toContain("treasury");
    const binance = providers.find((p) => p.id === "binance");
    expect(binance?.capabilities).toContain("orderbook");
    const defillama = providers.find((p) => p.id === "defillama");
    expect(defillama?.capabilities).toContain("tvl");
    const hyperliquid = providers.find((p) => p.id === "hyperliquid");
    expect(hyperliquid?.capabilities).toContain("funding");
    expect(providers.find((p) => p.id === "etherscan")?.capabilities).toContain("onchain");
    expect(providers.find((p) => p.id === "solscan")?.capabilities).toContain("onchain");
    expect(providers.find((p) => p.id === "coinglass")?.capabilities).toEqual(
      expect.arrayContaining(["liquidations", "long_short"]),
    );
  });

  it("rejects a request with no symbol", async () => {
    const result = await fetchMarketData({ capability: "quote" });
    expect(result.status).toBe("UNAVAILABLE");
  });

  it("normalizes a Yahoo quote", async () => {
    mockedYahoo.mockResolvedValueOnce({
      quotes: { AAPL: { symbol: "AAPL", price: 237.42, changePct: 1.2, prevClose: 235, volume: 1000 } },
    } as never);
    const result = await fetchMarketData({ capability: "quote", symbol: "AAPL", provider: "yahoo" });
    expect(result.status).toBe("OK");
    expect(result.provider).toBe("yahoo");
    expect((result.price as { price: number }).price).toBe(237.42);
  });

  it("honors a named provider (the Python router owns fallback)", async () => {
    mockedSafeGet.mockResolvedValueOnce({
      status: 200,
      contentType: "application/json",
      text: JSON.stringify({ lastPrice: "50000", priceChangePercent: "1.0" }),
      bytes: 40,
      url: "",
    } as never);
    const result = await fetchMarketData({ capability: "quote", symbol: "BTCUSDT", provider: "binance" });
    expect(result.status).toBe("OK");
    expect(result.provider).toBe("binance");
    expect((result.price as { price: number }).price).toBe(50000);
  });

  it("reports UNAVAILABLE when a provider fails", async () => {
    mockedYahoo.mockRejectedValueOnce(new Error("yahoo down"));
    const result = await fetchMarketData({ capability: "quote", symbol: "AAPL", provider: "yahoo" });
    expect(result.status).toBe("UNAVAILABLE");
  });

  it("maps a treasury yield from the FRED CSV", async () => {
    mockedSafeGet.mockResolvedValueOnce({
      status: 200,
      contentType: "text/csv",
      text: "DATE,DGS10\n2026-10-01,4.20\n2026-10-02,4.25\n",
      bytes: 40,
      url: "",
    } as never);
    const result = await fetchMarketData({ capability: "bonds", symbol: "US10Y", provider: "treasury" });
    expect(result.status).toBe("OK");
    expect(result.yield).toBe(4.25);
  });
});
