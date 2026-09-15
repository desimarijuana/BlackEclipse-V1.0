import { describe, it, expect } from "vitest";
import {
  parsePath,
  getPath,
  extractRecords,
  coerce,
  computeRecordKey,
  mapResponse,
  mapResponseDetailed,
  describeFields,
  type DatasetSchema,
} from "./mapping";

describe("parsePath", () => {
  it("splits nested and array paths", () => {
    expect(parsePath("data.quote.last")).toEqual(["data", "quote", "last"]);
    expect(parsePath("results[*]")).toEqual(["results", "*"]);
    expect(parsePath("$")).toEqual([]);
  });
});

describe("getPath", () => {
  it("reads nested values and reports missing keys", () => {
    const root = { data: { quote: { last: 237.42 } } };
    expect(getPath(root, "data.quote.last")).toEqual({ found: true, value: 237.42 });
    expect(getPath(root, "data.missing").found).toBe(false);
  });
});

describe("extractRecords", () => {
  const list = { results: [{ symbol: "AAPL" }, { symbol: "MSFT" }] };

  it("extracts array elements for recordPath=results[*]", () => {
    expect(extractRecords(list, "results[*]")).toHaveLength(2);
  });

  it("wraps a single root object for recordPath=$", () => {
    expect(extractRecords({ symbol: "AAPL" }, "$")).toEqual([{ symbol: "AAPL" }]);
  });

  it("returns nothing for a missing array", () => {
    expect(extractRecords({}, "results[*]")).toEqual([]);
  });
});

describe("coerce", () => {
  it("handles each field type", () => {
    expect(coerce("237.42", "number")).toBe(237.42);
    expect(coerce("1,234", "number")).toBe(1234);
    expect(coerce("bad", "number")).toBeUndefined();
    expect(coerce("yes", "boolean")).toBe(true);
    expect(coerce("0", "boolean")).toBe(false);
    expect(coerce(42, "string")).toBe("42");
    expect(coerce("2026-09-15T14:30:00Z", "datetime")).toBe("2026-09-15T14:30:00.000Z");
    expect(coerce("not-a-date", "datetime")).toBeUndefined();
    expect(coerce({ a: 1 }, "json")).toBe('{"a":1}');
  });
});

describe("computeRecordKey", () => {
  const fields = [
    { name: "symbol", type: "string" as const, sourcePath: "symbol", identity: true },
    { name: "timestamp", type: "datetime" as const, sourcePath: "ts", identity: true },
  ];

  it("joins identity fields deterministically", () => {
    expect(
      computeRecordKey({ symbol: "AAPL", timestamp: "2026-09-15T14:30:00.000Z" }, fields)
    ).toBe("AAPL|2026-09-15T14:30:00.000Z");
  });

  it("returns null when an identity value is missing", () => {
    expect(computeRecordKey({ symbol: "AAPL" }, fields)).toBeNull();
  });
});

describe("mapResponse", () => {
  const schema: DatasetSchema = {
    dataset: "market_prices",
    recordPath: "results[*]",
    fields: [
      { name: "symbol", type: "string", sourcePath: "ticker", identity: true },
      { name: "price", type: "number", sourcePath: "price" },
      { name: "volume", type: "number", sourcePath: "volume" },
    ],
  };

  it("maps nested fields and arrays", () => {
    const nested: DatasetSchema = {
      dataset: "quotes",
      recordPath: "$",
      fields: [
        { name: "symbol", type: "string", sourcePath: "data.symbol", identity: true },
        { name: "price", type: "number", sourcePath: "data.quote.last" },
      ],
    };
    const records = mapResponse({ data: { symbol: "AAPL", quote: { last: 237.42 } } }, nested);
    expect(records).toHaveLength(1);
    expect(records[0].values).toEqual({ symbol: "AAPL", price: 237.42 });
  });

  it("maps an array response into multiple records", () => {
    const records = mapResponse(
      { results: [
        { ticker: "AAPL", price: 237.42, volume: 18293421 },
        { ticker: "MSFT", price: 511.21, volume: 1000 },
      ] },
      schema
    );
    expect(records.map((r) => r.values.symbol)).toEqual(["AAPL", "MSFT"]);
    expect(records[0].recordKey).toBe("AAPL");
  });

  it("deduplicates within a batch (last write wins)", () => {
    const records = mapResponse(
      { results: [
        { ticker: "AAPL", price: 1, volume: 1 },
        { ticker: "AAPL", price: 2, volume: 2 },
      ] },
      schema
    );
    expect(records).toHaveLength(1);
    expect(records[0].values.price).toBe(2);
  });

  it("drops records with missing identity", () => {
    const records = mapResponse({ results: [{ price: 10 }] }, schema);
    expect(records).toHaveLength(0);
  });

  it("skips records missing required fields", () => {
    const required: DatasetSchema = {
      ...schema,
      fields: schema.fields.map((f) => ({ ...f, required: f.name === "price" })),
    };
    const records = mapResponse({ results: [{ ticker: "AAPL" }] }, required);
    expect(records).toHaveLength(0);
  });

  it("ignores invalid types on optional fields", () => {
    const records = mapResponse({ results: [{ ticker: "AAPL", price: "not-a-number" }] }, schema);
    expect(records).toHaveLength(1);
    expect(records[0].values.price).toBeUndefined();
  });
});

describe("mapResponseDetailed — honest accounting", () => {
  const schema: DatasetSchema = {
    dataset: "prices",
    recordPath: "results[*]",
    fields: [
      { name: "symbol", type: "string", sourcePath: "ticker", identity: true },
      { name: "price", type: "number", sourcePath: "price", required: true },
    ],
  };

  it("reports how many records the response contained", () => {
    const out = mapResponseDetailed(
      { results: [{ ticker: "AAPL", price: 1 }, { ticker: "MSFT", price: 2 }] },
      schema
    );
    expect(out.extracted).toBe(2);
    expect(out.records).toHaveLength(2);
    expect(out.rejectedRequired + out.rejectedIdentity + out.deduped).toBe(0);
  });

  it("counts records missing a required field", () => {
    const out = mapResponseDetailed(
      { results: [{ ticker: "AAPL", price: 1 }, { ticker: "MSFT" }] },
      schema
    );
    expect(out.extracted).toBe(2);
    expect(out.records).toHaveLength(1);
    expect(out.rejectedRequired).toBe(1);
  });

  it("counts records whose identity could not be computed", () => {
    const out = mapResponseDetailed({ results: [{ price: 1 }, { ticker: "MSFT", price: 2 }] }, schema);
    expect(out.rejectedIdentity).toBe(1);
    expect(out.records).toHaveLength(1);
  });

  it("counts collapsed duplicates instead of hiding them", () => {
    const out = mapResponseDetailed(
      { results: [{ ticker: "AAPL", price: 1 }, { ticker: "AAPL", price: 2 }] },
      schema
    );
    expect(out.extracted).toBe(2);
    expect(out.records).toHaveLength(1);
    expect(out.deduped).toBe(1);
  });

  it("accounts for every extracted record", () => {
    const out = mapResponseDetailed(
      {
        results: [
          { ticker: "AAPL", price: 1 },
          { ticker: "AAPL", price: 2 },
          { ticker: "MSFT" },
          { price: 9 },
        ],
      },
      schema
    );
    expect(out.extracted).toBe(4);
    const accounted = out.records.length + out.rejectedRequired + out.rejectedIdentity + out.deduped;
    expect(accounted).toBe(4);
  });
});

describe("describeFields", () => {
  it("enumerates nested and array paths", () => {
    const candidates = describeFields({ data: { symbol: "AAPL", quote: { last: 1 } }, results: [{ a: 1 }] });
    const paths = candidates.map((c) => c.path);
    expect(paths).toContain("data.symbol");
    expect(paths).toContain("data.quote.last");
    expect(paths).toContain("results[*].a");
  });

  it("reports scalar types", () => {
    const candidates = describeFields({ n: 1, s: "x", b: true, z: null });
    expect(candidates.find((c) => c.path === "n")?.type).toBe("number");
    expect(candidates.find((c) => c.path === "s")?.type).toBe("string");
    expect(candidates.find((c) => c.path === "b")?.type).toBe("boolean");
    expect(candidates.find((c) => c.path === "z")?.type).toBe("null");
  });
});
