import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Prisma (the module under test imports `prisma` from "@/lib/db").
const mAssetUpsert = vi.fn();
const mFindMany = vi.fn();
const mFindUnique = vi.fn();
const mUpdateMany = vi.fn();
const mTransaction = vi.fn((ops: Promise<unknown>[]) => Promise.all(ops));

vi.mock("@/lib/db", () => ({
  yieldToEventLoop: () => Promise.resolve(),
  prisma: {
    market: { upsert: () => Promise.resolve({ id: "m" }) },
    asset: {
      upsert: (...a: unknown[]) => mAssetUpsert(...a),
      findMany: (...a: unknown[]) => mFindMany(...a),
      updateMany: (...a: unknown[]) => mUpdateMany(...a),
    },
    price: {
      upsert: () => Promise.resolve({ id: "p" }),
    },
    systemConfig: {
      findUnique: (...a: unknown[]) => mFindUnique(...a),
      upsert: () => Promise.resolve({}),
    },
    $transaction: (ops: Promise<unknown>[]) => mTransaction(ops),
  },
}));

// Mock the TradingView fetcher module.
const mScan = vi.fn();
vi.mock("./fetchers/tradingview", () => ({
  scanMarket: (...a: unknown[]) => mScan(...a),
  // The cached path delegates to scanMarket — tests stub scanMarket and the
  // cache is per-process so every test gets a fresh call.
  getCachedMarketScan: async (market: string) => mScan(market),
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
    mFindMany
      .mockResolvedValueOnce([]) // pre-loop universe lookup (existing)
      .mockResolvedValue([{ id: "a1", symbol: "000001" }]); // post-upsert id map

    const r = await syncMarketUniverse("CN");
    expect(r.scanned).toBe(1);
    expect(r.created).toBe(1);
    expect(r.ok).toBe(1);
    expect(mAssetUpsert).toHaveBeenCalledTimes(1);
    // Upsert called with the CN market + symbol + create payload
    const arg = mAssetUpsert.mock.calls[0][0];
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

    const r = await syncMarketUniverse("CN");
    expect(r.created).toBe(0);
    expect(r.updated).toBe(1);
    expect(r.ok).toBe(1);
    expect(mAssetUpsert).toHaveBeenCalledTimes(1);
    // Update path sets isActive=true + refreshes name
    expect(mAssetUpsert.mock.calls[0][0].update.isActive).toBe(true);
    expect(mAssetUpsert.mock.calls[0][0].update.name).toBe("Ping An Bank");
  });

  it("writes in batched transactions rather than one await per row", async () => {
    const rows = Array.from({ length: 25 }, (_, i) =>
      baseRow({ symbol: `SYM${i}` })
    );
    mScan.mockResolvedValue(rows);
    // Pre-loop universe lookup is empty; the post-upsert id map resolves ids
    // for every scanned symbol so prices get written too.
    mFindMany.mockResolvedValueOnce([]);
    const idMap = rows.map((r, i) => ({ id: `a${i}`, symbol: r.symbol }));
    mFindMany.mockResolvedValue(idMap);

    await syncMarketUniverse("CN");
    // WRITE_CHUNK=500 → one transaction for assets + one for prices
    expect(mTransaction).toHaveBeenCalledTimes(2);
    expect(mTransaction.mock.calls[0][0]).toHaveLength(25); // assets
    expect(mTransaction.mock.calls[1][0]).toHaveLength(25); // prices
  });

  it("deactivates a symbol absent from the scan after DELIST_THRESHOLD misses", async () => {
    // One existing symbol NOT in the scan result.
    mFindMany
      .mockResolvedValueOnce([{ id: "a1", symbol: "999999", isActive: true }])
      .mockResolvedValue([{ id: "a1", symbol: "999999" }]);
    mFindUnique.mockResolvedValue({
      value: JSON.stringify({ 999999: DELIST_THRESHOLD - 1 }),
    });
    mUpdateMany.mockResolvedValue({ count: 1 });

    const r = await syncMarketUniverse("CN");
    expect(r.deactivated).toBe(1);
    expect(mUpdateMany).toHaveBeenCalledWith({
      where: { id: { in: ["a1"] } },
      data: { isActive: false },
    });
  });

  it("does NOT deactivate a symbol below the threshold", async () => {
    mFindMany.mockResolvedValue([
      { id: "a1", symbol: "999999", isActive: true },
    ]);
    mFindUnique.mockResolvedValue({
      value: JSON.stringify({ 999999: 0 }), // 0 prior misses, threshold=2
    });
    mUpdateMany.mockResolvedValue({ count: 1 });

    const r = await syncMarketUniverse("CN");
    expect(r.deactivated).toBe(0);
    expect(mUpdateMany).not.toHaveBeenCalled();
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
