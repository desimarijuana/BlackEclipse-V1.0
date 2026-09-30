// ─── MCP catalog front door (Phase 5E) ──────────────────────────────────────
// Thin typed wrapper over the Python runtime's /mcp endpoints. It adds no MCP
// logic — it forwards, and gates mutations with the same operator rule every
// other mutation uses. There is exactly one MCP manager, in Python.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";
import { checkMutationAllowed } from "@/lib/api-guard";
import type {
  MCPListResponse,
  MCPServerInput,
  MCPTestResult,
  MCPApprovalView,
  MCPIntegrationView,
  MCPInstallResult,
  MCPSupplyChainReport,
  MCPOauthTokenStatus,
  MCPWorkflowView,
  MCPDiagnosticsResponse,
  MCPVerifyResult,
  MCPCircuitView,
} from "./mcp-types";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 60_000, ...rest } = init;
  // The runtime authorizes MCP mutations by transport (loopback) or by this
  // secret — never by a body boolean. The value is never logged here.
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
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
 * Whether this request is an authorized operator, decided at the Next.js front
 * door: a same-origin browser request, a caller presenting the runtime secret,
 * or a loopback request. The Python runtime independently re-checks transport
 * and token, so a client cannot authorize itself with a body field.
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
  envKeys?: string[]
): Promise<MCPListResponse> {
  // A test connect can take a few seconds; allow headroom.
  const body = await request<MCPListResponse>("/mcp/servers", {
    method: "POST",
    timeoutMs: 60_000,
    body: JSON.stringify({ server, reload: true, envKeys }),
  });
  return body;
}

export async function deleteMCPServer(serverId: string): Promise<{ success: boolean; removed: string }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}`, { method: "DELETE" });
}

/** Connect + discover a candidate config WITHOUT persisting or activating it. */
export async function testMCPServer(server: MCPServerInput): Promise<MCPTestResult> {
  return request<MCPTestResult>("/mcp/servers/test", {
    method: "POST",
    timeoutMs: 60_000,
    body: JSON.stringify({ server }),
  });
}

/** Operator reset of a server's circuit breaker (back to CLOSED). */
export async function resetMCPCircuit(
  serverId: string
): Promise<{ success: boolean; serverId: string; circuit: MCPCircuitView }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}/circuit/reset`, {
    method: "POST",
    timeoutMs: 30_000,
  });
}

/** Record the operator's review of a server's current catalog digest. */
export async function confirmMCPCatalog(serverId: string): Promise<MCPListResponse> {
  return request<MCPListResponse>(`/mcp/servers/${encodeURIComponent(serverId)}/confirm`, {
    method: "POST",
    timeoutMs: 60_000,
  });
}

/**
 * Operator-triggered credential verification: ONE bounded read call proving the
 * server's credentials actually work. Separate from Test (which only proves the
 * process started and listed tools), never automatic, and the body is never
 * returned — only a content-free verdict (`credentials_valid` /
 * `credentials_rejected` / `verify_inconclusive`).
 */
export async function verifyMCPServer(
  serverId: string,
  tool: string,
  args: Record<string, unknown> = {}
): Promise<MCPVerifyResult> {
  return request<MCPVerifyResult>(`/mcp/servers/${encodeURIComponent(serverId)}/verify`, {
    method: "POST",
    timeoutMs: 30_000,
    body: JSON.stringify({ tool, arguments: args }),
  });
}

export async function reloadMCP(): Promise<MCPListResponse> {
  return request<MCPListResponse>("/mcp/reload", { method: "POST", timeoutMs: 60_000 });
}

// ── Finance presets, workflows, diagnostics (product layer) ─────────────────

export async function listMCPIntegrations(): Promise<MCPIntegrationView[]> {
  const body = await request<{ integrations: MCPIntegrationView[] }>("/mcp/integrations", { method: "GET" });
  return body.integrations ?? [];
}

export async function listMCPWorkflows(): Promise<MCPWorkflowView[]> {
  const body = await request<{ workflows: MCPWorkflowView[] }>("/mcp/workflows", { method: "GET" });
  return body.workflows ?? [];
}

/** Install a preset integration as a DISABLED, nothing-selected server. */
export async function installMCPIntegration(integrationId: string): Promise<MCPInstallResult> {
  return request<MCPInstallResult>(
    `/mcp/integrations/${encodeURIComponent(integrationId)}/install`,
    { method: "POST", timeoutMs: 30_000 }
  );
}

/** The offline, read-only supply-chain report (never triggers a network call). */
export async function getMCPSupplyChain(): Promise<MCPSupplyChainReport> {
  return request<MCPSupplyChainReport>("/mcp/supply-chain", { method: "GET" });
}

export async function getMCPDiagnostics(
  knownSecrets: string[] = [],
  tokenStatus: Record<string, MCPOauthTokenStatus> = {}
): Promise<MCPDiagnosticsResponse> {
  return request<MCPDiagnosticsResponse>("/mcp/diagnostics", {
    method: "POST",
    timeoutMs: 30_000,
    // Secret NAMES and OAuth token STATUS only — never values. Lets the runtime
    // check references and report auth state.
    body: JSON.stringify({ knownSecrets, tokenStatus }),
  });
}

// ── OAuth lifecycle (Milestone 3) ───────────────────────────────────────────

export async function mcpOauthLogin(serverId: string, scope = ""): Promise<{ success: boolean; verificationUri?: string; userCode?: string }> {
  const body = await request<{ success: boolean; verificationUri?: string; userCode?: string }>(
    `/mcp/servers/${encodeURIComponent(serverId)}/login`,
    { method: "POST", body: JSON.stringify({ scope }) }
  );
  return body;
}

export async function mcpOauthLogout(serverId: string): Promise<{ success: boolean; removed: boolean }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}/logout`, { method: "POST" });
}

// ── Effectful-tool approvals (5G) ───────────────────────────────────────────

export async function listMCPApprovals(status?: string): Promise<MCPApprovalView[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await request<{ approvals: MCPApprovalView[] }>(`/mcp/approvals${query}`, { method: "GET" });
  return body.approvals ?? [];
}

export async function decideMCPApproval(
  approvalId: string,
  approve: boolean,
  reason = ""
): Promise<MCPApprovalView> {
  const body = await request<{ approval: MCPApprovalView }>(
    `/mcp/approvals/${encodeURIComponent(approvalId)}/decide`,
    { method: "POST", body: JSON.stringify({ approve, reason }) }
  );
  return body.approval;
}
