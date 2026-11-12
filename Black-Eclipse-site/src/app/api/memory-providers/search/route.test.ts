import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/memory-providers/search. It reaches the
// Python runtime (503 mapping) and performs an OUTBOUND external call when
// allowExternal is set, so it is operator-gated.

const memoryProviderSearch = vi.fn();

vi.mock("@/lib/harness/clients/eclipse-memory-client", () => ({
  memoryProviderSearch: (...a: unknown[]) => memoryProviderSearch(...a),
}));

import { POST } from "@/app/api/memory-providers/search/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/clients/python-client";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/memory-providers/search", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/memory-providers/search", () => {
  beforeEach(() => memoryProviderSearch.mockReset());

  it("refuses a cross-origin request before calling the runtime", async () => {
    const res = await POST(req({ query: "x" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(memoryProviderSearch).not.toHaveBeenCalled();
  });

  it("returns 503 when the Python runtime is unavailable", async () => {
    memoryProviderSearch.mockRejectedValueOnce(new HarnessRuntimeUnavailable("runtime down"));
    const res = await POST(req({ query: "x" }));
    expect(res.status).toBe(503);
  });

  it("forwards the search and returns the runtime body", async () => {
    memoryProviderSearch.mockResolvedValueOnce({ results: [], native: 0, external: 0 });
    const res = await POST(req({ query: "x", allowExternal: true }));
    expect(res.status).toBe(200);
    expect(memoryProviderSearch).toHaveBeenCalledWith(expect.objectContaining({ query: "x", allowExternal: true }));
  });
});
