import { describe, it, expect, vi, beforeEach } from "vitest";
import { expandValues, valuesFor, MAX_VALUES_PER_PULL } from "./refresh";

// Prisma + registry are mocked so these tests exercise the expansion/clamping
// logic without touching the network or the real jdds.db.

const connectorCalls: Array<Record<string, string>> = [];
let fetchShouldFail = false;

const datasetRow = {
  id: "ds1",
  name: "tickers",
  connectorId: "c1",
  recordPath: "$",
  pullParams: JSON.stringify({ symbol: "BTC" }),
  refreshEnabled: false,
  refreshIntervalMin: 60,
  lastRefreshAt: null,
  nextRefreshAt: null,
  timestampField: null,
  description: null,
  createdAt: new Date(),
  updatedAt: new Date(),
  fields: [
    { name: "symbol", fieldType: "string", sourcePath: "symbol", required: false, identity: true, unit: null, description: null, position: 0 },
    { name: "price", fieldType: "number", sourcePath: "price", required: false, identity: false, unit: null, description: null, position: 1 },
  ],
};

vi.mock("@/lib/db", () => ({
  prisma: {
    customDataset: {
      findUnique: vi.fn(async () => datasetRow),
      findMany: vi.fn(async () => [datasetRow]),
      update: vi.fn(async () => datasetRow),
    },
    dataConnector: {
      findUnique: vi.fn(async () => ({
        params: JSON.stringify([{ name: "symbol", value: "{{symbol}}", required: true }]),
      })),
      findMany: vi.fn(async () => []),
    },
    customDatasetRecord: { upsert: vi.fn(async () => ({})) },
    cronJob: { upsert: vi.fn(async () => ({})) },
  },
}));

vi.mock("./registry", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./registry")>()),
  getConnector: vi.fn(() => ({
    id: "custom:c1",
    name: "Test API",
    capabilities: ["PRICE"],
    kind: "custom",
    isConfigured: () => true,
    async test() {
      return { ok: true, state: "CONNECTED", message: "ok" };
    },
    async fetch(request: { capability: string; params?: Record<string, string> }) {
      connectorCalls.push({ ...(request.params ?? {}) });
      if (fetchShouldFail) {
        return {
          ok: false,
          error: { code: "http_error", message: "HTTP 500" },
          provenance: "UNAVAILABLE",
          source: "Test API",
          retrievedAt: new Date().toISOString(),
        };
      }
      return {
        ok: true,
        data: { symbol: (request.params ?? {}).symbol, price: 1 },
        provenance: "LIVE",
        source: "Test API",
        retrievedAt: new Date().toISOString(),
      };
    },
  })),
}));

vi.mock("./builtins", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./builtins")>()),
  registerBuiltinConnectors: vi.fn(),
}));

describe("expandValues", () => {
  it("splits comma-separated values and trims", () => {
    expect(expandValues("BTC, ETH ,SOL")).toEqual(["BTC", "ETH", "SOL"]);
  });

  it("returns a single value as a one-element list", () => {
    expect(expandValues("AAPL")).toEqual(["AAPL"]);
  });

  it("drops empty entries", () => {
    expect(expandValues("BTC,,ETH,")).toEqual(["BTC", "ETH"]);
    expect(expandValues("")).toEqual([]);
    expect(expandValues("  ,  ")).toEqual([]);
  });
});

describe("valuesFor", () => {
  it("prefers an explicitly provided list", () => {
    expect(valuesFor({ name: "symbol", value: "{{symbol}}" }, "A,B")).toEqual(["A", "B"]);
  });

  it("uses a declared literal when nothing is provided", () => {
    expect(valuesFor({ name: "interval", value: "1d" })).toEqual(["1d"]);
  });

  it("returns nothing for a template with no supplied value", () => {
    expect(valuesFor({ name: "symbol", value: "{{symbol}}" })).toEqual([]);
  });
});

describe("pullDataset", () => {
  beforeEach(() => {
    connectorCalls.length = 0;
    fetchShouldFail = false;
    vi.clearAllMocks();
  });

  it("makes one request per comma-separated value", async () => {
    const { pullDataset } = await import("./refresh");
    const summary = await pullDataset("ds1", { values: { symbol: "BTC,ETH,SOL" }, delayMs: 0 });
    expect(summary.attempted).toBe(3);
    expect(summary.succeeded).toBe(3);
    expect(connectorCalls.map((c) => c.symbol)).toEqual(["BTC", "ETH", "SOL"]);
    expect(summary.written).toBe(3);
  });

  it("falls back to the dataset's saved pullParams", async () => {
    const { pullDataset } = await import("./refresh");
    const summary = await pullDataset("ds1");
    expect(connectorCalls.map((c) => c.symbol)).toEqual(["BTC"]);
    expect(summary.attempted).toBe(1);
  });

  it("clamps to MAX_VALUES_PER_PULL and reports the overflow", async () => {
    const { pullDataset } = await import("./refresh");
    const many = Array.from({ length: MAX_VALUES_PER_PULL + 10 }, (_, i) => `S${i}`).join(",");
    const summary = await pullDataset("ds1", { values: { symbol: many }, delayMs: 0 });
    expect(summary.attempted).toBe(MAX_VALUES_PER_PULL);
    expect(summary.overflow).toBe(10);
    expect(summary.truncated).toBe(true);
    expect(connectorCalls).toHaveLength(MAX_VALUES_PER_PULL);
  });

  it("reports a partial failure honestly instead of claiming success", async () => {
    const { pullDataset } = await import("./refresh");
    // First succeeds, then fail the rest.
    let calls = 0;
    const { getConnector } = await import("./registry");
    vi.mocked(getConnector).mockReturnValueOnce({
      id: "custom:c1",
      name: "Test API",
      capabilities: ["PRICE"],
      kind: "custom",
      isConfigured: () => true,
      async test() {
        return { ok: true, state: "CONNECTED", message: "ok" };
      },
      async fetch(request: { capability: string; params?: Record<string, string> }) {
        connectorCalls.push({ ...(request.params ?? {}) });
        calls++;
        if (calls === 1) {
          return {
            ok: true,
            data: { symbol: "BTC", price: 1 },
            provenance: "LIVE",
            source: "Test API",
            retrievedAt: new Date().toISOString(),
          };
        }
        return {
          ok: false,
          error: { code: "http_error", message: "HTTP 500" },
          provenance: "UNAVAILABLE",
          source: "Test API",
          retrievedAt: new Date().toISOString(),
        };
      },
    } as never);
    const summary = await pullDataset("ds1", { values: { symbol: "A,B,C" }, delayMs: 0 });
    expect(summary.attempted).toBe(3);
    expect(summary.succeeded).toBe(1);
    expect(summary.failed).toBe(2);
    expect(summary.results.filter((r) => !r.ok)).toHaveLength(2);
  });

  it("throws a clear error when a template has no value", async () => {
    const { pullDataset } = await import("./refresh");
    await expect(pullDataset("ds1", { values: {} })).rejects.toThrow(/Missing value/);
  });
});

describe("refresh scheduler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("refreshes only datasets whose interval has elapsed", async () => {
    const { prisma } = await import("@/lib/db");
    const { runDueDatasetRefreshes, resetDatasetRefreshState } = await import("./refresh-scheduler");
    resetDatasetRefreshState();

    // Not due: last refresh was just now.
    vi.mocked(prisma.customDataset.findMany).mockResolvedValueOnce([
      { ...datasetRow, refreshEnabled: true, lastRefreshAt: new Date() },
    ] as never);
    const notDue = await runDueDatasetRefreshes();
    expect(notDue.refreshed).toBe(0);

    // Due: last refresh was well beyond the interval.
    vi.mocked(prisma.customDataset.findMany).mockResolvedValueOnce([
      { ...datasetRow, refreshEnabled: true, lastRefreshAt: new Date(Date.now() - 3 * 60 * 60_000) },
    ] as never);
    const due = await runDueDatasetRefreshes();
    expect(due.refreshed).toBe(1);
  });

  it("advances the clock even when a dataset fails, so it cannot hot-loop", async () => {
    const { prisma } = await import("@/lib/db");
    const { runDueDatasetRefreshes, resetDatasetRefreshState } = await import("./refresh-scheduler");
    resetDatasetRefreshState();
    fetchShouldFail = true;

    vi.mocked(prisma.customDataset.findMany).mockResolvedValueOnce([
      { ...datasetRow, refreshEnabled: true, lastRefreshAt: null },
    ] as never);
    const result = await runDueDatasetRefreshes();
    expect(result.failed).toBe(1);
    expect(vi.mocked(prisma.customDataset.update)).toHaveBeenCalled();
    fetchShouldFail = false;
  });

  it("force refreshes regardless of the interval", async () => {
    const { prisma } = await import("@/lib/db");
    const { runDueDatasetRefreshes, resetDatasetRefreshState } = await import("./refresh-scheduler");
    resetDatasetRefreshState();
    vi.mocked(prisma.customDataset.findMany).mockResolvedValueOnce([
      { ...datasetRow, refreshEnabled: true, lastRefreshAt: new Date() },
    ] as never);
    const forced = await runDueDatasetRefreshes({ force: true });
    expect(forced.refreshed).toBe(1);
  });
});
