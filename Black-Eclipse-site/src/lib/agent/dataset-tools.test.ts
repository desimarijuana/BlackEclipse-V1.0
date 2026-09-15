import { describe, it, expect, vi, beforeEach } from "vitest";

// Dataset query helpers + agent dataset tools.
// Prisma is mocked so the tests never touch the real jdds.db.

const datasetRows = [
  {
    id: "ds1",
    name: "binance_tickers",
    description: "Public ticker data",
    recordPath: "$",
    connectorId: "c1",
    timestampField: null,
    createdAt: new Date(),
    updatedAt: new Date(),
    fields: [
      { name: "symbol", fieldType: "string", sourcePath: "symbol", required: false, identity: true, unit: null, description: null, position: 0 },
      { name: "price", fieldType: "number", sourcePath: "lastPrice", required: false, identity: false, unit: null, description: null, position: 1 },
    ],
  },
];

const recordRows = [
  { id: "r1", datasetId: "ds1", recordKey: "BTCUSDT", values: JSON.stringify({ symbol: "BTCUSDT", price: 76000.5 }), provenance: "CUSTOM", retrievedAt: new Date() },
  { id: "r2", datasetId: "ds1", recordKey: "ETHUSDT", values: JSON.stringify({ symbol: "ETHUSDT", price: 2400.1 }), provenance: "CUSTOM", retrievedAt: new Date() },
  { id: "r3", datasetId: "ds1", recordKey: "AAPL", values: JSON.stringify({ symbol: "AAPL", price: 237.42 }), provenance: "LIVE", retrievedAt: new Date() },
];

vi.mock("@/lib/db", () => ({
  prisma: {
    customDataset: {
      findMany: vi.fn(async () => datasetRows.map((d) => ({ ...d, _count: { records: recordRows.length } }))),
      findFirst: vi.fn(async ({ where }: { where: { name: string } }) =>
        datasetRows.find((d) => d.name === where.name) ?? null
      ),
    },
    customDatasetRecord: {
      findMany: vi.fn(async () => recordRows),
    },
  },
}));

describe("dataset query helpers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns dataset summaries with fields and counts", async () => {
    const { datasetSummaries } = await import("@/lib/connectors/store");
    const summaries = await datasetSummaries();
    expect(summaries).toHaveLength(1);
    expect(summaries[0].name).toBe("binance_tickers");
    expect(summaries[0].recordCount).toBe(3);
    expect(summaries[0].fields[0]).toEqual({ name: "symbol", type: "string", identity: true });
  });

  it("queries records without filters", async () => {
    const { queryRecords } = await import("@/lib/connectors/store");
    const records = await queryRecords("ds1", { limit: 10 });
    expect(records).toHaveLength(3);
    expect(records[0].values).toEqual({ symbol: "BTCUSDT", price: 76000.5 });
  });

  it("filters records by mapped field values (case-insensitive)", async () => {
    const { queryRecords } = await import("@/lib/connectors/store");
    const records = await queryRecords("ds1", { filters: { symbol: "aapl" } });
    expect(records).toHaveLength(1);
    expect(records[0].recordKey).toBe("AAPL");
  });

  it("returns nothing when a filter matches no record", async () => {
    const { queryRecords } = await import("@/lib/connectors/store");
    expect(await queryRecords("ds1", { filters: { symbol: "NOPE" } })).toHaveLength(0);
  });

  it("clamps limit to a sane range", async () => {
    const { prisma } = await import("@/lib/db");
    const { queryRecords } = await import("@/lib/connectors/store");
    await queryRecords("ds1", { limit: 9999 });
    const call = vi.mocked(prisma.customDatasetRecord.findMany).mock.calls.at(-1)?.[0] as { take: number };
    expect(call.take).toBe(100);
  });

  it("finds a dataset by name", async () => {
    const { findDatasetByName } = await import("@/lib/connectors/store");
    expect((await findDatasetByName("binance_tickers"))?.id).toBe("ds1");
    expect(await findDatasetByName("missing")).toBeNull();
  });
});

describe("agent dataset tools", () => {
  it("exposes list_datasets, describe_dataset and query_dataset", async () => {
    const { DATASET_TOOLS, datasetToolSchemas } = await import("./dataset-tools");
    const names = DATASET_TOOLS.map((t) => t.name);
    expect(names).toEqual(["list_datasets", "describe_dataset", "query_dataset"]);
    expect(datasetToolSchemas()).toHaveLength(3);
  });

  it("list_datasets reports names, fields and record counts", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("list_datasets")!.execute({});
    expect(out).toContain("binance_tickers");
    expect(out).toContain("symbol:string (identity)");
    expect(out).toContain("Records: 3");
  });

  it("describe_dataset reports schema details", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("describe_dataset")!.execute({ dataset: "binance_tickers" });
    expect(out).toContain("recordPath: $");
    expect(out).toContain("price (number)");
  });

  it("describe_dataset handles an unknown name by listing alternatives", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("describe_dataset")!.execute({ dataset: "nope" });
    expect(out).toContain('No dataset named "nope"');
    expect(out).toContain("binance_tickers");
  });

  it("query_dataset returns records with provenance stated", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("query_dataset")!.execute({ dataset: "binance_tickers", limit: 10 });
    expect(out).toContain("3 record(s)");
    expect(out).toContain("Provenance: CUSTOM");
    expect(out).toContain("operator data source, not the built-in scraper");
  });

  it("query_dataset applies filters and reports the filter text", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("query_dataset")!.execute({
      dataset: "binance_tickers",
      filters: { symbol: "AAPL" },
    });
    expect(out).toContain("matching symbol=AAPL");
    expect(out).toContain("AAPL");
    expect(out).not.toContain("BTCUSDT");
  });

  it("query_dataset is honest when nothing matches", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("query_dataset")!.execute({
      dataset: "binance_tickers",
      filters: { symbol: "ZZZZ" },
    });
    expect(out).toContain("no records matching");
  });

  it("tolerates malformed filter arguments", async () => {
    const { getDatasetTool } = await import("./dataset-tools");
    const out = await getDatasetTool("query_dataset")!.execute({ dataset: "binance_tickers", filters: "not-an-object" });
    expect(out).toContain("record(s)");
  });
});

describe("agent tool registry", () => {
  it("includes the dataset tools alongside the built-ins", async () => {
    const { TOOLS, getTool, toolSchemas } = await import("./tools");
    const names = TOOLS.map((t) => t.name);
    expect(names).toContain("get_price");
    expect(names).toContain("query_dataset");
    expect(getTool("list_datasets")).toBeDefined();
    expect(toolSchemas().some((s) => s.function.name === "query_dataset")).toBe(true);
  });
});
