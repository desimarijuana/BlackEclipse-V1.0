import { describe, it, expect, vi, beforeEach } from "vitest";

// Phase 16 remainder: the operator-declared dataset capability
// (`custom_dataset_records`), wired through the REAL dispatcher
// (`fetchCapability`) and a REAL custom REST connector (fake transport).
// JDDS reads (dataset lookup/schema/registry sync) are mocked; the connector
// platform's URL building, parameter filling and record mapping are real, so
// this exercises the actual read path offline.

const findDataset = vi.fn();
const getSchema = vi.fn();
const loadRegistry = vi.fn();

vi.mock("@/lib/db", () => ({ prisma: {} }));
vi.mock("@/lib/connectors/store", () => ({
  findDatasetByName: (...a: unknown[]) => findDataset(...a),
  getDatasetSchema: (...a: unknown[]) => getSchema(...a),
  loadConnectorsIntoRegistry: (...a: unknown[]) => loadRegistry(...a),
}));

import { fetchCapability } from "../data-bridge";
import { clearRegistry, registerConnector } from "@/lib/connectors/registry";
import { buildCustomRestConnector } from "@/lib/connectors/custom-rest";

const transport = vi.fn();

function registerTestConnector(): void {
  registerConnector(
    buildCustomRestConnector(
      {
        id: "test-api",
        name: "Test API",
        baseUrl: "https://api.example.com",
        path: "/v1/rows",
        capabilities: ["CUSTOM_DATASET"],
        params: [{ name: "symbol", value: "{{symbol}}", required: true }],
        auth: { scheme: "none" },
        enabled: true,
      },
      { transport: (...a: Parameters<typeof transport>) => transport(...a) },
    ),
  );
}

const SCHEMA = {
  id: "ds1",
  connectorId: "test-api",
  dataset: "orders",
  recordPath: "data",
  fields: [
    { name: "symbol", type: "string" as const, sourcePath: "symbol", required: true, identity: true },
    { name: "qty", type: "number" as const, sourcePath: "size" },
  ],
};

function okJson(data: unknown) {
  const text = JSON.stringify(data);
  return {
    status: 200,
    contentType: "application/json",
    url: "https://api.example.com/v1/rows",
    text,
    bytes: text.length,
  };
}

function lastUrl(): string {
  return String((transport.mock.calls[0][0] as { url: string }).url);
}

beforeEach(() => {
  clearRegistry();
  transport.mockReset();
  findDataset.mockReset();
  getSchema.mockReset();
  loadRegistry.mockReset();
  loadRegistry.mockResolvedValue(undefined);
  findDataset.mockResolvedValue({ id: "ds1", name: "orders", connectorId: "test-api" });
  getSchema.mockResolvedValue(SCHEMA);
  registerTestConnector();
});

describe("fetchCapability — custom_dataset_records (Phase 16)", () => {
  it("collects mapped records through the operator's declared connector", async () => {
    transport.mockResolvedValue(
      okJson({
        data: [
          { symbol: "BTC", size: 2.5 },
          { symbol: "ETH", size: "1" },
        ],
      }),
    );

    const result = await fetchCapability("custom_dataset_records", {
      dataset: "orders",
      values: { symbol: "BTC,ETH" },
    });
    expect(result.status).toBe("OK");
    expect(result.provenance).toBe("LIVE");
    expect(result.fields).toEqual(["symbol", "qty"]);
    expect(result.count).toBe(2);
    expect(result.truncated).toBe(false);

    const records = result.records as Array<{ recordKey: string; values: Record<string, unknown> }>;
    expect(records.map((r) => r.recordKey)).toEqual(["BTC", "ETH"]);
    // The mapping layer coerced the string "1" to a number via the schema.
    expect(records[0].values).toEqual({ symbol: "BTC", qty: 2.5 });
    expect(records[1].values.qty).toBe(1);

    // The connector built the request from ITS declared parameter only —
    // caller values are percent-encoded into the operator's template.
    expect(lastUrl()).toContain("symbol=BTC%2CETH");
  });

  it("accepts a values JSON string", async () => {
    transport.mockResolvedValue(okJson({ data: [{ symbol: "ETH", size: 1 }] }));
    const result = await fetchCapability("custom_dataset_records", {
      dataset: "orders",
      values: '{"symbol": "ETH"}',
    });
    expect(result.status).toBe("OK");
    expect(lastUrl()).toContain("symbol=ETH");
  });

  it("an undeclared dataset is not_found — only what the operator declared is reachable", async () => {
    findDataset.mockResolvedValue(null);
    const result = await fetchCapability("custom_dataset_records", { dataset: "nope" });
    expect(result.failureClass).toBe("not_found");
    expect(transport).not.toHaveBeenCalled();
  });

  it("a missing or disabled connector is not_found, never a silent empty pull", async () => {
    clearRegistry();
    const result = await fetchCapability("custom_dataset_records", {
      dataset: "orders",
      values: { symbol: "X" },
    });
    expect(result.failureClass).toBe("not_found");
    expect(transport).not.toHaveBeenCalled();
  });

  it("a dataset with no connector attached is refused as incomplete", async () => {
    findDataset.mockResolvedValue({ id: "ds1", name: "orders", connectorId: null });
    const result = await fetchCapability("custom_dataset_records", { dataset: "orders" });
    expect(result.failureClass).toBe("incomplete");
  });

  it("refuses nested values; a missing required parameter fails before the transport", async () => {
    const nested = await fetchCapability("custom_dataset_records", {
      dataset: "orders",
      values: { symbol: { deep: 1 } },
    });
    expect(nested.failureClass).toBe("invalid_request");
    expect(transport).not.toHaveBeenCalled();

    const missing = await fetchCapability("custom_dataset_records", { dataset: "orders" });
    expect(missing.failureClass).toBe("source_failure");
    expect(String(missing.error)).toContain("symbol");
    expect(transport).not.toHaveBeenCalled();
  });

  it("a connector HTTP failure is source_failure", async () => {
    transport.mockResolvedValue({ status: 500, contentType: null, url: "https://api.example.com/v1/rows", text: "", bytes: 0 });
    const result = await fetchCapability("custom_dataset_records", {
      dataset: "orders",
      values: { symbol: "X" },
    });
    expect(result.failureClass).toBe("source_failure");
    expect(result.status).toBe("UNAVAILABLE");
  });
});
