import { describe, it, expect, vi, beforeEach } from "vitest";

// The install route is the front door for the one-click preset install. It must
// gate the mutation, forward to the Python runtime, and never claim success when
// the runtime refused. This locks that contract at the route layer.

const installMCPIntegration = vi.fn();

vi.mock("@/lib/harness/clients/mcp-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/harness/clients/mcp-client")>();
  return { ...actual, installMCPIntegration: (...args: unknown[]) => installMCPIntegration(...args) };
});

import { POST } from "@/app/api/harness/mcp/integrations/[id]/install/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/clients/python-client";

function request(headers: Record<string, string> = {}): Request {
  return new Request("http://localhost:3000/api/harness/mcp/integrations/filesystem/install", {
    method: "POST",
    headers: { origin: "http://localhost:3000", ...headers },
  });
}

const params = Promise.resolve({ id: "filesystem" });

describe("POST /api/harness/mcp/integrations/[id]/install", () => {
  beforeEach(() => installMCPIntegration.mockReset());

  it("forwards a same-origin install and reports the disabled-entry result", async () => {
    installMCPIntegration.mockResolvedValueOnce({
      success: true,
      installed: "filesystem",
      config: { enabled: false, selected_tools: [] },
    });
    const res = await POST(request(), { params });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(installMCPIntegration).toHaveBeenCalledWith("filesystem");
    expect(body.success).toBe(true);
    expect(body.config.enabled).toBe(false);
  });

  it("returns 503 when the Python runtime is unavailable", async () => {
    installMCPIntegration.mockRejectedValueOnce(
      new HarnessRuntimeUnavailable("The Python agent runtime is not available.")
    );
    const res = await POST(request(), { params });
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toMatch(/runtime is not available/i);
  });

  it("rejects a cross-origin request before calling the runtime", async () => {
    const res = await POST(request({ origin: "http://evil.example" }), { params });
    expect(res.status).toBe(403);
    expect(installMCPIntegration).not.toHaveBeenCalled();
  });
});
