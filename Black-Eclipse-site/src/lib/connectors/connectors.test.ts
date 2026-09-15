import { describe, it, expect, beforeEach, vi } from "vitest";
import { registerConnector, clearRegistry, connectorsForCapability, getConnector, listConnectors } from "./registry";
import { resolveConnectors, resolvePrimary } from "./resolver";
import type { DataConnector, ConnectorResult } from "./types";
import { parseBinanceTicker, toBinancePair, cryptoConnector } from "./providers/crypto";

function stub(id: string, kind: "builtin" | "custom", capabilities: DataConnector["capabilities"], configured = true): DataConnector {
  return {
    id,
    name: id,
    capabilities,
    kind,
    isConfigured: () => configured,
    async test() {
      return { ok: true, state: "CONNECTED", message: "ok" };
    },
    async fetch(): Promise<ConnectorResult> {
      return { ok: true, data: null, provenance: "LIVE", source: id, retrievedAt: new Date().toISOString() };
    },
  };
}

describe("connector registry", () => {
  beforeEach(() => clearRegistry());

  it("registers and looks up connectors", () => {
    registerConnector(stub("a", "builtin", ["PRICE"]));
    expect(getConnector("a")?.id).toBe("a");
    expect(listConnectors()).toHaveLength(1);
  });

  it("replaces a connector with the same id", () => {
    registerConnector(stub("a", "builtin", ["PRICE"]));
    registerConnector(stub("a", "custom", ["NEWS"]));
    expect(listConnectors()).toHaveLength(1);
    expect(getConnector("a")?.capabilities).toEqual(["NEWS"]);
  });

  it("filters by capability and configuration", () => {
    registerConnector(stub("price", "builtin", ["PRICE"]));
    registerConnector(stub("price2", "builtin", ["PRICE"], false));
    registerConnector(stub("news", "builtin", ["NEWS"]));
    expect(connectorsForCapability("PRICE").map((c) => c.id)).toEqual(["price"]);
  });
});

describe("capability resolver", () => {
  beforeEach(() => {
    clearRegistry();
    registerConnector(stub("custom:z", "custom", ["PRICE"]));
    registerConnector(stub("builtin:a", "builtin", ["PRICE"]));
    registerConnector(stub("custom:a", "custom", ["PRICE"]));
    registerConnector(stub("news", "builtin", ["NEWS"]));
  });

  it("orders built-ins before operator connectors deterministically", () => {
    expect(resolveConnectors({ capability: "PRICE" }).map((c) => c.id)).toEqual([
      "builtin:a",
      "custom:a",
      "custom:z",
    ]);
  });

  it("returns no connectors for an unprovided capability", () => {
    expect(resolveConnectors({ capability: "OHLCV" })).toEqual([]);
    expect(resolvePrimary({ capability: "OHLCV" })).toBeUndefined();
  });

  it("never fabricates a provider for an empty capability", () => {
    const resolved = resolveConnectors({ capability: "CUSTOM_DATASET" });
    expect(resolved).toEqual([]);
  });
});

describe("crypto connector", () => {
  it("normalizes symbols to Binance pairs", () => {
    expect(toBinancePair("btc")).toBe("BTCUSDT");
    expect(toBinancePair("BTCUSDT")).toBe("BTCUSDT");
    expect(toBinancePair(" eth ")).toBe("ETHUSDT");
  });

  it("parses a ticker into a scraper-shaped quote", () => {
    const result = parseBinanceTicker("BTC", {
      lastPrice: "104321.5",
      priceChangePercent: "2.5",
      quoteVolume: "123456",
    });
    expect(result.status).toBe("ok");
    expect(result.quote).toMatchObject({ symbol: "BTC", price: 104321.5, changePct: 2.5, volume: 123456 });
    expect(result.source).toBe("crypto");
  });

  it("returns empty for a zero/missing price", () => {
    expect(parseBinanceTicker("BTC", { lastPrice: "0" }).status).toBe("empty");
    expect(parseBinanceTicker("BTC", null).status).toBe("empty");
  });

  it("declares PRICE and is configured", () => {
    expect(cryptoConnector.capabilities).toContain("PRICE");
    expect(cryptoConnector.isConfigured()).toBe(true);
  });

  it("rejects unsupported capabilities", async () => {
    const result = await cryptoConnector.fetch({ capability: "NEWS" });
    expect(result.ok).toBe(false);
    expect(result.provenance).toBe("UNAVAILABLE");
  });

  it("requires a symbol", async () => {
    const result = await cryptoConnector.fetch({ capability: "PRICE", params: {} });
    expect(result.error?.code).toBe("missing_param");
  });
});

describe("crypto scraper facade parity", () => {
  it("maps a connector success back to a FetchResult", async () => {
    vi.resetModules();
    const cryptoMod = await import("./providers/crypto");
    const spy = vi.spyOn(cryptoMod.cryptoConnector, "fetch").mockResolvedValue({
      ok: true,
      data: { symbol: "BTC", price: 100, changePct: 1, volume: 5 },
      provenance: "LIVE",
      source: "crypto",
      retrievedAt: new Date().toISOString(),
    });
    const facade = await import("../scraper/fetchers/crypto");
    const result = await facade.fetchCryptoQuote("BTC");
    expect(result.status).toBe("ok");
    expect(result.quote?.price).toBe(100);
    expect(result.source).toBe("crypto");
    spy.mockRestore();
  });
});
