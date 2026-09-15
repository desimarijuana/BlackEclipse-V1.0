import { describe, it, expect, vi, beforeEach } from "vitest";

// Data-integrity guarantee: custom dataset ingestion must never touch canonical
// market tables (Asset / Price / Candles). We mock the Prisma client and assert
// exactly which tables the store writes to.

const canonicalWrites: string[] = [];
const recordUpserts: Array<{ where: unknown; create: unknown; update: unknown }> = [];

const fieldRows = [
  { name: "symbol", fieldType: "string", sourcePath: "ticker", required: false, identity: true, unit: null, description: null, position: 0 },
  { name: "price", fieldType: "number", sourcePath: "price", required: false, identity: false, unit: null, description: null, position: 1 },
];

vi.mock("@/lib/db", () => ({
  prisma: {
    dataConnector: {
      findMany: vi.fn(async () => []),
      findUnique: vi.fn(async () => null),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
    customDataset: {
      findUnique: vi.fn(async () => ({
        id: "ds1",
        connectorId: null,
        name: "market_prices",
        description: null,
        recordPath: "results[*]",
        timestampField: null,
        fields: fieldRows,
      })),
      upsert: vi.fn(),
      findMany: vi.fn(async () => []),
    },
    customDatasetField: {
      deleteMany: vi.fn(),
      createMany: vi.fn(),
    },
    customDatasetRecord: {
      upsert: vi.fn(async (args: unknown) => {
        recordUpserts.push(args as never);
        return {};
      }),
      findMany: vi.fn(async () => []),
    },
    // Canonical tables — any call is a failure and is recorded.
    asset: {
      upsert: vi.fn(() => {
        canonicalWrites.push("asset.upsert");
        return {};
      }),
      update: vi.fn(() => {
        canonicalWrites.push("asset.update");
        return {};
      }),
      create: vi.fn(() => {
        canonicalWrites.push("asset.create");
        return {};
      }),
    },
    price: {
      upsert: vi.fn(() => {
        canonicalWrites.push("price.upsert");
        return {};
      }),
      update: vi.fn(() => {
        canonicalWrites.push("price.update");
        return {};
      }),
    },
    candles: {
      upsert: vi.fn(() => {
        canonicalWrites.push("candles.upsert");
        return {};
      }),
      create: vi.fn(() => {
        canonicalWrites.push("candles.create");
        return {};
      }),
    },
  },
}));

describe("custom dataset ingestion", () => {
  beforeEach(() => {
    canonicalWrites.length = 0;
    recordUpserts.length = 0;
  });

  it("writes only to CustomDatasetRecord, never canonical tables", async () => {
    const { ingestRecords } = await import("./store");
    const outcome = await ingestRecords("ds1", {
      results: [
        { ticker: "AAPL", price: 237.42 },
        { ticker: "MSFT", price: 511.21 },
      ],
    });
    expect(outcome.written).toBe(2);
    expect(recordUpserts).toHaveLength(2);
    expect(canonicalWrites).toEqual([]);
  });

  it("upserts on the (datasetId, recordKey) unique key — idempotent", async () => {
    const { ingestRecords } = await import("./store");
    const payload = { results: [{ ticker: "AAPL", price: 237.42 }] };
    await ingestRecords("ds1", payload);
    await ingestRecords("ds1", payload);
    expect(recordUpserts).toHaveLength(2);
    for (const call of recordUpserts) {
      expect((call.where as { datasetId_recordKey: { datasetId: string; recordKey: string } }).datasetId_recordKey.datasetId).toBe("ds1");
      expect((call.where as { datasetId_recordKey: { recordKey: string } }).datasetId_recordKey.recordKey).toBe("AAPL");
    }
  });

  it("stores values as a JSON string, not an object", async () => {
    const { ingestRecords } = await import("./store");
    await ingestRecords("ds1", { results: [{ ticker: "AAPL", price: 237.42 }] });
    const create = recordUpserts[0].create as { values: unknown };
    expect(typeof create.values).toBe("string");
    expect(JSON.parse(create.values as string)).toEqual({ symbol: "AAPL", price: 237.42 });
  });

  it("carries provenance on every record", async () => {
    const { ingestRecords } = await import("./store");
    await ingestRecords("ds1", { results: [{ ticker: "AAPL", price: 1 }] }, "LIVE");
    const create = recordUpserts[0].create as { provenance: string };
    expect(create.provenance).toBe("LIVE");
  });

  it("reports honest counts instead of a blanket success", async () => {
    const { ingestRecords } = await import("./store");
    const outcome = await ingestRecords("ds1", {
      results: [
        { ticker: "AAPL", price: 1 },
        { ticker: "AAPL", price: 2 }, // duplicate key
        { price: 9 }, // no identity
      ],
    });
    expect(outcome.extracted).toBe(3);
    expect(outcome.written).toBe(1);
    expect(outcome.deduped).toBe(1);
    expect(outcome.rejectedIdentity).toBe(1);
    expect(outcome.rejected).toBe(1);
    // Every extracted row is accounted for as written/deduped/rejected.
    expect(outcome.written + outcome.deduped + outcome.rejected).toBe(3);
  });
});

describe("public connector projection", () => {
  it("never exposes the encrypted secret", async () => {
    const { toPublicConnector } = await import("./store");
    const view = toPublicConnector({
      id: "c1",
      name: "My API",
      description: null,
      baseUrl: "https://api.example.com",
      path: "/quote",
      capabilities: JSON.stringify(["PRICE"]),
      params: "[]",
      headers: "{}",
      authScheme: "api_key",
      authHeader: "X-API-Key",
      authUsername: null,
      secretEncrypted: "v1.abc.def.ghi",
      enabled: true,
      healthState: "CONNECTED",
      lastTested: null,
      lastSuccess: null,
      lastError: null,
      lastHttpStatus: 200,
      lastLatencyMs: 40,
    });
    expect(JSON.stringify(view)).not.toContain("v1.abc.def.ghi");
    expect(view.hasSecret).toBe(true);
  });
});
