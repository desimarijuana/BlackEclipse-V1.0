import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/harness/data — the capability allowlist is
// the ONE gate between the Python runtime and the read-only JDdS bridge. A
// capability the dispatcher handles but this list omits returns HTTP 400
// ("capability must be one of …"), which Python reports as `bridge HTTP 400` /
// UNAVAILABLE. `response_contract` shipped without its allowlist entry, so
// every `response_block_schema` / `response_validate` call failed until the
// entry was added — these tests pin it stays reachable.

const fetchCapability = vi.fn(async (_capability: unknown, _params: unknown) => ({
  status: "OK",
  op: "schema",
  blocks: [{ type: "infographic", fields: [] }],
  iconKeys: ["trend-up", "chart"],
}));

vi.mock("@/lib/harness", () => ({
  fetchCapability: (capability: unknown, params: unknown) => fetchCapability(capability, params),
}));

import { POST } from "@/app/api/harness/data/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/harness/data", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

beforeEach(() => fetchCapability.mockClear());

describe("POST /api/harness/data — capability allowlist", () => {
  it("routes response_contract to the bridge (regression: missing entry → 400)", async () => {
    const res = await POST(req({ capability: "response_contract", params: { op: "schema" } }));
    expect(res.status).toBe(200);
    expect(fetchCapability).toHaveBeenCalledWith("response_contract", { op: "schema" });
    const body = await res.json();
    expect(body.status).toBe("OK");
  });

  it("routes the Phase-16 collection capabilities to the bridge", async () => {
    for (const capability of ["sec_filing_list", "custom_dataset_records"]) {
      const res = await POST(req({ capability, params: {} }));
      expect(res.status).toBe(200);
      expect(fetchCapability).toHaveBeenCalledWith(capability, {});
    }
  });

  it("rejects a capability that is not allowlisted before dispatching", async () => {
    const res = await POST(req({ capability: "drop-tables" }));
    expect(res.status).toBe(400);
    expect(fetchCapability).not.toHaveBeenCalled();
    const body = await res.json();
    expect(body.error).toContain("response_contract");
  });

  it("refuses a cross-origin call before any capability runs", async () => {
    const res = await POST(req({ capability: "response_contract" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(fetchCapability).not.toHaveBeenCalled();
  });
});
