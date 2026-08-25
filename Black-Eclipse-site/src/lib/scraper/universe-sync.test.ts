import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Prisma (the module under test imports `prisma` from "@/lib/db").
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mUpsert = vi.fn();
const mFindMany = vi.fn();
const mFindUnique = vi.fn();
const mUpdate = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    market: { upsert: () => Promise.resolve({ id: "m" }) },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    asset: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      upsert: (...a: any[]) => mUpsert(...a),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      findMany: (...a: any[]) => mFindMany(...a),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      update: (...a: any[]) => mUpdate(...a),
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    price: {
      upsert: () => Promise.resolve({ id: "p" }),
    },
    systemConfig: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      findUnique: (...a: any[]) => mFindUnique(...a),
      upsert: () => Promise.resolve({}),
    },
  },
}));

// Mock scanMarket + isTradingViewMarket from the fetcher module.
const mScan = vi.fn();
vi.mock("./fetchers/tradingview", () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  scanMarket: (...a: any[]) => mScan(...a),
  isTradingViewMarket: (m: string) => m !== "US",
}));

import { syncMarketUniverse, DELIST_THRESHOLD } from "./universe-sync";

const baseRow = (over = {}) => ({
  symbol: "000001",
  exchange: "SZSE",
  name: "Ping An Bank",
  price: 11.63,
  changePct: 0.6,
  marketCap: 2.2e11,
  volume: 5e7,
  peRatio: 5.4,
  eps: 2.13,
  dividendYield: 3.5,
  fiftyTwoWeekHigh: 14.0,
  fiftyTwoWeekLow: 9.0,
  beta: 0.8,
  sector: "Finance",
  industry: "Banks",
  yahooSymbol: "000001.SZ",
  ...over,
});

describe("universe-sync", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mScan.mockResolvedValue([baseRow()]);
    mFindUnique.mockResolvedValue(null); // no stored misses
  });

  it("creates a new asset + price when the symbol is not in JDDS", async () => {
    mFindMany.mockResolvedValue([]); // empty universe
    mUpsert.mockResolvedValue({ id: "a1" }); // upsert created (no existing)

    const r = await syncMarketUniverse("CN");
    expect(r.scanned).toBe(1);
    expect(r.created).toBe(1);
    expect(r.ok).toBe(1);
    expect(mUpsert).toHaveBeenCalledTimes(1);
    // Upsert called with the CN market + symbol + create payload
    const arg = mUpsert.mock.calls[0][0];
    expect(arg.where.marketId_symbol.marketId).toBe("CN");
    expect(arg.where.marketId_symbol.symbol).toBe("000001");
    expect(arg.create.marketId).toBe("CN");
    expect(arg.create.symbol).toBe("000001");
    expect(arg.create.isActive).toBe(true);
  });

  it("updates an existing asset + price when the symbol already exists", async () => {
    mFindMany.mockResolvedValue([
      { id: "a1", symbol: "000001", isActive: true },
    ]);
    mUpsert.mockResolvedValue({ id: "a1" });

    const r = await syncMarketUniverse("CN");
    expect(r.created).toBe(0);
    expect(r.updated).toBe(1);
    expect(r.ok).toBe(1);
    expect(mUpsert).toHaveBeenCalledTimes(1);
    // Update path sets isActive=true + refreshes name
    expect(mUpsert.mock.calls[0][0].update.isActive).toBe(true);
    expect(mUpsert.mock.calls[0][0].update.name).toBe("Ping An Bank");
  });

  it("deactivates a symbol absent from the scan after DELIST_THRESHOLD misses", async () => {
    // One existing symbol NOT in the scan result.
    mFindMany.mockResolvedValue([
      { id: "a1", symbol: "999999", isActive: true },
    ]);
    mFindUnique.mockResolvedValue({
      value: JSON.stringify({ 999999: DELIST_THRESHOLD - 1 }),
    });
    mUpdate.mockResolvedValue({ id: "a1" }); // deactivation update

    const r = await syncMarketUniverse("CN");
    expect(r.deactivated).toBe(1);
    // The deactivation update is the one that flips isActive=false.
    const deactCall = mUpdate.mock.calls.find(
      (c) => c[0].data?.isActive === false
    );
    expect(deactCall).toBeTruthy();
  });

  it("does NOT deactivate a symbol below the threshold", async () => {
    mFindMany.mockResolvedValue([
      { id: "a1", symbol: "999999", isActive: true },
    ]);
    mFindUnique.mockResolvedValue({
      value: JSON.stringify({ 999999: 0 }), // 0 prior misses, threshold=2
    });
    mUpdate.mockResolvedValue({ id: "a1" });

    const r = await syncMarketUniverse("CN");
    expect(r.deactivated).toBe(0);
    const anyDeact = mUpdate.mock.calls.some(
      (c) => c[0].data?.isActive === false
    );
    expect(anyDeact).toBe(false);
  });

  it("no-ops for a non-TradingView market (US stays on yfinance)", async () => {
    const r = await syncMarketUniverse("US");
    expect(r.scanned).toBe(0);
    expect(r.ok).toBe(0);
    expect(mScan).not.toHaveBeenCalled();
  });

  it("returns empty summary when the scan fails (no crash)", async () => {
    mScan.mockRejectedValue(new Error("rate limited"));
    mFindMany.mockResolvedValue([]);
    const r = await syncMarketUniverse("CN");
    expect(r.scanned).toBe(0);
    expect(r.ok).toBe(0);
  });
});
