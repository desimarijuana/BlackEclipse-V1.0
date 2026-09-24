// ─── MCP catalog front door (Phase 5E) ──────────────────────────────────────
// Thin typed wrapper over the Python runtime's /mcp endpoints. It adds no MCP
// logic — it forwards, and gates mutations with the same operator rule every
// other mutation uses. There is exactly one MCP manager, in Python.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";
import { checkMutationAllowed } from "@/lib/api-guard";
import type { MCPListResponse, MCPServerInput, MCPTestResult } from "./mcp-types";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 60_000, ...rest } = init;
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(rest.headers ?? {}) },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

/**
 * Whether this request is an authorized operator.
 *
 * Operator actions (add/test/enable/disable/remove) are gated exactly like every
 * other mutation in this repo: `checkMutationAllowed` — a same-origin browser
 * request OR a caller presenting the runtime secret OR a request to a loopback
 * host. The Python runtime re-enforces the same check, so this is defense in
 * depth. The proxy sets `operator` server-side; a client cannot claim it.
 */
export function isOperatorRequest(request?: Request): boolean {
  if (!request) return false;
  return checkMutationAllowed(request).allowed;
}

export async function listMCPServers(): Promise<MCPListResponse> {
  const body = await request<MCPListResponse>("/mcp/servers", { method: "GET" });
  return {
    success: Boolean(body.success),
    servers: body.servers ?? [],
    configured: body.configured ?? 0,
    connected: body.connected ?? 0,
    registeredTools: body.registeredTools ?? 0,
    loadDiagnostics: body.loadDiagnostics ?? [],
  };
}

export async function upsertMCPServer(
  server: MCPServerInput,
  operator: boolean,
  envKeys?: string[]
): Promise<MCPListResponse> {
  // A test connect can take a few seconds; allow headroom.
  const body = await request<MCPListResponse>("/mcp/servers", {
    method: "POST",
    timeoutMs: 60_000,
    body: JSON.stringify({ operator, server, reload: true, envKeys }),
  });
  return body;
}

export async function deleteMCPServer(serverId: string, operator: boolean): Promise<{ success: boolean; removed: string }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}`, {
    method: "DELETE",
    body: JSON.stringify({ operator }),
  });
}

/** Connect + discover a candidate config WITHOUT persisting or activating it. */
export async function testMCPServer(server: MCPServerInput, operator: boolean): Promise<MCPTestResult> {
  return request<MCPTestResult>("/mcp/servers/test", {
    method: "POST",
    timeoutMs: 60_000,
    body: JSON.stringify({ operator, server }),
  });
}

export async function reloadMCP(operator: boolean): Promise<MCPListResponse> {
  return request<MCPListResponse>("/mcp/reload", {
    method: "POST",
    timeoutMs: 60_000,
    body: JSON.stringify({ operator }),
  });
}
