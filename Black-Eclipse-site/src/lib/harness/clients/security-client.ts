// ─── Security subsystem front door ───────────────────────────────────────────
// Typed wrapper over the Python runtime's `/security/*` routes. The Python
// Security Gateway is the ONE decision path for every privileged operation; this
// module is the operator surface (inspect status/policy/audit, issue & revoke
// capabilities, decide approvals). It never resolves a secret VALUE — the API
// does not expose one.

import { HARNESS_PY_URL, ensurePythonRuntime } from "../python-runtime";
import { runtimeCallbackToken } from "../runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "../errors";

export type SecurityDecision = "allow" | "deny" | "approval_required";

export interface SecurityStatus {
  profile: string;
  policyVersion: number;
  floor: Array<{ name: string; verdict: string; reason?: string }>;
  network: { default: string; rules: Array<Record<string, unknown>> };
  secrets: Record<string, unknown>;
  audit: SecurityAuditSummary;
  approvals: Record<string, unknown>;
}

export interface SecurityAuditEvent {
  id: string;
  timestamp: number;
  category: string;
  type: string;
  action?: string | null;
  resource?: string | null;
  decision?: string | null;
  risk?: string | null;
  policy?: string | null;
  sessionId?: string | null;
}

export interface SecurityAuditSummary {
  counters: Record<string, number>;
  audit: { total: number; byDecision: Record<string, number>; byCategory: Record<string, number> };
  chain: { valid: boolean; checked: number };
}

export interface SecurityCapability {
  id: string;
  subject: string;
  action: string;
  resource: string;
  scope: string;
  expiresAt?: number | null;
  active: boolean;
}

export interface DecisionResult {
  decision: SecurityDecision;
  reason: string;
  risk: string;
  policy: string;
  matchedRules: string[];
  approvalId?: string | null;
  capabilityId?: string | null;
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 60_000, ...rest } = init;
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

export async function getSecurityStatus(): Promise<SecurityStatus> {
  const body = await request<{ success: boolean } & SecurityStatus>("/security/status");
  return body;
}

export async function listSecurityAudit(limit = 100): Promise<SecurityAuditEvent[]> {
  const body = await request<{ events: SecurityAuditEvent[] }>(`/security/audit?limit=${limit}`);
  return body.events ?? [];
}

export async function verifySecurityAudit(): Promise<{ valid: boolean; checked: number }> {
  return request<{ valid: boolean; checked: number }>("/security/audit/verify");
}

export async function checkSecurityRequest(payload: Record<string, unknown>): Promise<DecisionResult> {
  const body = await request<{ decision: DecisionResult }>("/security/check", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.decision;
}

export async function checkSecurityNetwork(url: string): Promise<DecisionResult> {
  const body = await request<{ decision: DecisionResult }>("/security/network/check", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  return body.decision;
}

export async function listSecurityCapabilities(): Promise<SecurityCapability[]> {
  const body = await request<{ capabilities: SecurityCapability[] }>("/security/capabilities");
  return body.capabilities ?? [];
}

export async function issueSecurityCapability(payload: Record<string, unknown>): Promise<SecurityCapability> {
  const body = await request<{ capability: SecurityCapability }>("/security/capabilities", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.capability;
}

export async function revokeSecurityCapability(capabilityId: string): Promise<boolean> {
  await request<{ success: boolean }>(`/security/capabilities/${encodeURIComponent(capabilityId)}/revoke`, {
    method: "POST",
  });
  return true;
}

export async function listSecurityApprovals(limit = 100): Promise<Array<Record<string, unknown>>> {
  const body = await request<{ approvals: Array<Record<string, unknown>> }>(`/security/approvals?limit=${limit}`);
  return body.approvals ?? [];
}

export async function decideSecurityApproval(
  approvalId: string,
  approve: boolean,
  options: { remember?: boolean; reason?: string } = {}
): Promise<Record<string, unknown>> {
  const body = await request<{ approval: Record<string, unknown> }>(
    `/security/approvals/${encodeURIComponent(approvalId)}/decide`,
    { method: "POST", body: JSON.stringify({ approve, ...options }) }
  );
  return body.approval;
}

export async function reloadSecurityPolicy(
  policy: Record<string, unknown>,
  profile?: string
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/security/policy/reload", {
    method: "POST",
    body: JSON.stringify({ policy, profile }),
  });
}
