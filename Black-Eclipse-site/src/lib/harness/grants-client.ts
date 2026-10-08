// ─── Standing-grant front door ──────────────────────────────────────────────
// Thin typed wrapper over the Python runtime's /grants endpoints. A standing
// grant is an explicit, revocable "always allow" permission (one program/tool in
// one workspace) that removes the approval PROMPT. It never bypasses the effect
// classification: a denied command is still refused. Grants are created only by
// an "always allow" decision on a real pending approval — this module lists and
// revokes them.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export interface StandingGrant {
  id: string;
  kind: string;
  scope: string;
  pattern: string;
  label?: string | null;
  risk?: string | null;
  source?: string | null;
  createdBy?: string | null;
  createdAt: string;
  lastUsedAt?: string | null;
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

export async function listStandingGrants(scope?: string): Promise<StandingGrant[]> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  const body = await request<{ grants: StandingGrant[] }>(`/grants${query}`, { method: "GET" });
  return body.grants ?? [];
}

export async function revokeStandingGrant(grantId: string): Promise<boolean> {
  const body = await request<{ revoked?: string }>(
    `/grants/${encodeURIComponent(grantId)}/revoke`,
    { method: "POST" }
  );
  return Boolean(body.revoked);
}
