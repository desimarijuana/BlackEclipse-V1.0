import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/scraper/datasets — the one route through
// which the Python runtime hands COLLECTED rows back to the vault.
//
// Three things must hold: the rows land in the custom-dataset store (never in
// a canonical market table), every row carries a stable content key (so a
// re-run updates in place instead of duplicating), and the route refuses a
// payload it cannot store honestly.

const saveDataset = vi.fn(async (input: { name: string }) => ({ id: "ds1", name: input.name }));
const ingestRecords = vi.fn(async (_id: string, raw: unknown, provenance: string) => {
  const rows = (raw as { rows?: unknown[] }).rows ?? [];
  return { written: rows.length, extracted: rows.length, rejected: 0, rejectedRequired: 0, rejectedIdentity: 0, deduped: 0, provenance };
});

vi.mock("@/lib/connectors/store", () => ({
  saveDataset: (input: unknown) => saveDataset(input as { name: string }),
  ingestRecords: (id: string, raw: unknown, provenance: string) => ingestRecords(id, raw, provenance),
}));

import { POST } from "@/app/api/scraper/datasets/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/scraper/datasets", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  saveDataset.mockClear();
  ingestRecords.mockClear();
});

describe("POST /api/scraper/datasets", () => {
  it("stores the rows as a dataset labelled SCRAPER", async () => {
    const res = await POST(req({
      name: "psx holdings",
      sourceUrl: "https://example.com/holdings",
      purpose: "track the index weights",
      columns: ["name", "weight"],
      rows: [{ name: "ACME", weight: "4.5" }],
    }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.provenance).toBe("SCRAPER");
    expect(body.dataset.name).toBe("scraped_psx_holdings");
    expect(saveDataset).toHaveBeenCalledTimes(1);
    expect(ingestRecords).toHaveBeenCalledTimes(1);
    expect(ingestRecords.mock.calls[0][2]).toBe("SCRAPER");
  });

  it("gives every row a stable content key so a re-run updates in place", async () => {
    await POST(req({
      name: "x",
      columns: ["a"],
      rows: [{ a: "1" }, { a: "2" }],
    }));
    const raw = ingestRecords.mock.calls[0][1] as { rows: Array<Record<string, string>> };
    expect(raw.rows).toHaveLength(2);
    for (const row of raw.rows) {
      expect(typeof row.record_key).toBe("string");
      expect(row.record_key.length).toBeGreaterThan(0);
    }
    expect(raw.rows[0].record_key).not.toBe(raw.rows[1].record_key);
  });

  it("refuses a payload with no name, no columns or no rows list", async () => {
    for (const body of [
      { columns: ["a"], rows: [] },
      { name: "x", rows: [] },
      { name: "x", columns: ["a"] },
    ]) {
      const res = await POST(req(body));
      expect(res.status).toBe(400);
    }
    expect(saveDataset).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin call before anything is stored", async () => {
    const res = await POST(
      req({ name: "x", columns: ["a"], rows: [] }, "http://evil.example"),
    );
    expect(res.status).toBe(403);
    expect(saveDataset).not.toHaveBeenCalled();
  });
});
