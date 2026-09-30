import { describe, it, expect, vi, beforeEach } from "vitest";

// The verify route is the operator-triggered credential check. It must gate the
// mutation, require a tool, forward to the Python runtime, and never claim a
// result the runtime did not return. It must never be automatic.

const verifyMCPServer = vi.fn();

vi.mock("@/lib/harness/mcp-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/harness/mcp-client")>();
  return { ...actual, verifyMCPServer: (...args: unknown[]) => verifyMCPServer(...args) };
});

import { POST } from "@/app/api/harness/mcp/servers/[id]/verify/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/python-client";

function request(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost:3000/api/harness/mcp/servers/notion/verify", {
    method: "POST",
    headers: { origin: "http://localhost:3000", "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

const params = Promise.resolve({ id: "notion" });

describe("POST /api/harness/mcp/servers/[id]/verify", () => {
  beforeEach(() => verifyMCPServer.mockReset());

  it("forwards a same-origin verify and reports the verdict", async () => {
    verifyMCPServer.mockResolvedValueOnce({
      code: "credentials_rejected",
      verifiedAt: "2026-09-30T00:00:00Z",
      tool: "API-get-self",
      bounded: true,
      providerStatus: 401,
      providerCode: "unauthorized",
    });
    const res = await POST(request({ tool: "API-get-self", arguments: {} }), { params });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(verifyMCPServer).toHaveBeenCalledWith("notion", "API-get-self", {});
    expect(body.code).toBe("credentials_rejected");
    expect(body.providerStatus).toBe(401);
  });

  it("rejects a missing tool before calling the runtime", async () => {
    const res = await POST(request({ arguments: {} }), { params });
    expect(res.status).toBe(400);
    expect(verifyMCPServer).not.toHaveBeenCalled();
  });

  it("returns 503 when the Python runtime is unavailable", async () => {
    verifyMCPServer.mockRejectedValueOnce(
      new HarnessRuntimeUnavailable("The Python agent runtime is not available.")
    );
    const res = await POST(request({ tool: "API-get-self" }), { params });
    expect(res.status).toBe(503);
  });

  it("rejects a cross-origin request before calling the runtime", async () => {
    const res = await POST(request({ tool: "API-get-self" }, { origin: "http://evil.example" }), { params });
    expect(res.status).toBe(403);
    expect(verifyMCPServer).not.toHaveBeenCalled();
  });
});
