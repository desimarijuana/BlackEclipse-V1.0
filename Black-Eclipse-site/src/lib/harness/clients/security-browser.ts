// ─── Security BROWSER client ─────────────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/security/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: no Node process or
// filesystem APIs, and no server-only runtime bootstrap (that lives in the
// server-only `security-client.ts`). Fetch only.

import type {
  DecisionResult,
  SecurityAuditEvent,
  SecurityCapability,
  SecurityStatus,
} from "./security-client";

// Type-only re-exports — erased at compile time, so no server code ships.
export type { DecisionResult, SecurityAuditEvent, SecurityCapability, SecurityStatus };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function getSecurityStatus(): Promise<SecurityStatus> {
  return api<SecurityStatus>("/api/security/status");
}

export async function listSecurityAudit(limit = 100): Promise<SecurityAuditEvent[]> {
  const body = await api<{ events: SecurityAuditEvent[] }>(`/api/security/audit?limit=${limit}`);
  return body.events ?? [];
}

export async function verifySecurityAudit(): Promise<{ valid: boolean; checked: number }> {
  return api<{ valid: boolean; checked: number }>("/api/security/audit/verify");
}

export async function checkSecurityRequest(payload: Record<string, unknown>): Promise<DecisionResult> {
  const body = await api<{ decision: DecisionResult }>("/api/security/check", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.decision;
}

export async function checkSecurityNetwork(url: string): Promise<DecisionResult> {
  const body = await api<{ decision: DecisionResult }>("/api/security/network/check", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  return body.decision;
}

export async function listSecurityCapabilities(): Promise<SecurityCapability[]> {
  const body = await api<{ capabilities: SecurityCapability[] }>("/api/security/capabilities");
  return body.capabilities ?? [];
}

export async function issueSecurityCapability(payload: Record<string, unknown>): Promise<SecurityCapability> {
  const body = await api<{ capability: SecurityCapability }>("/api/security/capabilities", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.capability;
}

export async function revokeSecurityCapability(capabilityId: string): Promise<boolean> {
  await api(`/api/security/capabilities/${encodeURIComponent(capabilityId)}/revoke`, { method: "POST" });
  return true;
}

export async function listSecurityApprovals(limit = 100): Promise<Array<Record<string, unknown>>> {
  const body = await api<{ approvals: Array<Record<string, unknown>> }>(`/api/security/approvals?limit=${limit}`);
  return body.approvals ?? [];
}

export async function decideSecurityApproval(
  approvalId: string,
  approve: boolean,
  options: { remember?: boolean; reason?: string } = {}
): Promise<Record<string, unknown>> {
  const body = await api<{ approval: Record<string, unknown> }>(
    `/api/security/approvals/${encodeURIComponent(approvalId)}/decide`,
    { method: "POST", body: JSON.stringify({ approve, ...options }) }
  );
  return body.approval;
}

export async function reloadSecurityPolicy(
  policy: Record<string, unknown>,
  profile?: string
): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>("/api/security/policy/reload", {
    method: "POST",
    body: JSON.stringify({ policy, profile }),
  });
}
