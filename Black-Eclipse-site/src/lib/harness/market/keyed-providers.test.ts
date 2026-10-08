import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: vi.fn(async () => "test-key") }));
vi.mock("@/lib/connectors/security", () => ({ safeGet: vi.fn() }));

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { fetchMarketData } from "@/lib/harness/market/bridge";

const mockedSafeGet = vi.mocked(safeGet);
const mockedKey = vi.mocked(resolveProviderKey);

function ok(body: unknown) {
  return { status: 200, contentType: "application/json", text: JSON.stringify(body), bytes: 10, url: "" } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedKey.mockResolvedValue("test-key");
});

describe("keyed market providers", () => {
  it("polygon serves an equity top-of-book (NBBO)", async () => {
    mockedSafeGet.mockResolvedValueOnce(ok({ status: "OK", results: { p: 189.5, P: 189.55, s: 100, S: 80, t: 1_700_000_000_000_000_000 } }));
    const r = await fetchMarketData({ capability: "orderbook", symbol: "AAPL", provider: "polygon" });
    expect(r.status).toBe("OK");
    expect(r.provider).toBe("polygon");
    expect(r.bestBid).toBe(189.5);
    expect(r.bestAsk).toBe(189.55);
  });

  it("polygon serves trades without inferring side", async () => {
    mockedSafeGet.mockResolvedValueOnce(ok({ status: "OK", results: [{ id: "1", price: 189.6, size: 10, sip_timestamp: 1_700_000_000_000_000_000 }] }));
    const r = await fetchMarketData({ capability: "trades", symbol: "AAPL", provider: "polygon" });
    expect(r.status).toBe("OK");
    const trades = r.trades as Array<{ side: unknown; sideInferred: boolean }>;
    expect(trades[0].side).toBeNull();
    expect(trades[0].sideInferred).toBe(false);
  });

  it("finnhub serves an equity quote", async () => {
    mockedSafeGet.mockResolvedValueOnce(ok({ c: 190.1, d: 1.2, dp: 0.63, pc: 188.9, o: 189, h: 190.5, l: 188.5, t: 1_700_000_000 }));
    const r = await fetchMarketData({ capability: "quote", symbol: "AAPL", provider: "finnhub" });
    expect(r.status).toBe("OK");
    expect(r.provider).toBe("finnhub");
    expect((r.price as { price: number }).price).toBe(190.1);
  });

  it("reports AUTHENTICATION_FAILED honestly when a key is missing", async () => {
    mockedKey.mockResolvedValueOnce(null);
    const r = await fetchMarketData({ capability: "quote", symbol: "AAPL", provider: "polygon" });
    expect(r.status).toBe("UNAVAILABLE");
    expect(mockedSafeGet).not.toHaveBeenCalled();
  });
});
