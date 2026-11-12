// ─── Standing-grant BROWSER client ───────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/harness/grants/**`), which proxy
// to the Python runtime. This module MUST stay client-safe: no `child_process`,
// no `fs`, no `ensurePythonRuntime` (that lives in the server-only
// `grants-client.ts`). Fetch only. Without this split the standing-grants panel
// cannot be mounted from a client component — importing the server client pulls
// `child_process` into the browser bundle and the page fails to compile.

import type { StandingGrant } from './grants-client';

// Type-only re-export — erased at compile time, so no server code ships.
export type { StandingGrant };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function listStandingGrants(scope?: string): Promise<StandingGrant[]> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : '';
  const body = await api<{ grants: StandingGrant[] }>(`/api/harness/grants${query}`);
  return body.grants ?? [];
}

export async function revokeStandingGrant(grantId: string): Promise<boolean> {
  const body = await api<{ revoked?: string | boolean }>(
    `/api/harness/grants/${encodeURIComponent(grantId)}/revoke`,
    { method: 'POST' },
  );
  return Boolean(body.revoked);
}
