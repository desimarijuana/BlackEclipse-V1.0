import { describe, it, expect, vi, beforeEach } from "vitest";

// The circuit-reset route is the operator action that clears a tripped breaker.
// It must gate the mutation, forward to the Python runtime, and never claim
// success when the runtime refused.

const resetMCPCircuit = vi.fn();

vi.mock("@/lib/harness/clients/mcp-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/harness/clients/mcp-client")>();
  return { ...actual, resetMCPCircuit: (...args: unknown[]) => resetMCPCircuit(...args) };
});

import { POST } from "@/app/api/harness/mcp/servers/[id]/circuit/reset/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/clients/python-client";

function request(headers: Record<string, string> = {}): Request {
  return new Request("http://localhost:3000/api/harness/mcp/servers/raw/circuit/reset", {
    method: "POST",
    headers: { origin: "http://localhost:3000", ...headers },
  });
}

const params = Promise.resolve({ id: "raw" });

describe("POST /api/harness/mcp/servers/[id]/circuit/reset", () => {
  beforeEach(() => resetMCPCircuit.mockReset());

  it("forwards a same-origin reset and reports the cleared breaker", async () => {
    resetMCPCircuit.mockResolvedValueOnce({
      success: true,
      serverId: "raw",
      circuit: { state: "closed", failures: 0, threshold: 3 },
    });
    const res = await POST(request(), { params });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(resetMCPCircuit).toHaveBeenCalledWith("raw");
    expect(body.success).toBe(true);
    expect(body.circuit.state).toBe("closed");
  });

  it("returns 503 when the Python runtime is unavailable", async () => {
    resetMCPCircuit.mockRejectedValueOnce(
      new HarnessRuntimeUnavailable("The Python agent runtime is not available.")
    );
    const res = await POST(request(), { params });
    expect(res.status).toBe(503);
  });

  it("rejects a cross-origin request before calling the runtime", async () => {
    const res = await POST(request({ origin: "http://evil.example" }), { params });
    expect(res.status).toBe(403);
    expect(resetMCPCircuit).not.toHaveBeenCalled();
  });
});
