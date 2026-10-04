// ─── Model Runtime BROWSER client ───────────────────────────────────────────
// The Model Control Center talks to the Next.js API routes (`/api/harness/
// model-runtime/**`), which proxy to the Python runtime. This module MUST stay
// client-safe: no `child_process`, no `fs`, no `ensurePythonRuntime` (that lives
// in the server-only `model-runtime-client.ts`). Fetch only.

import type {
  CapabilityState,
  PricingKind,
  RuntimeHealthView,
  RuntimeModelView,
  RuntimeProviderView,
  RuntimeRouteDecisionView,
  RuntimeRoutingView,
  RuntimeUsageView,
  RouteQuery,
} from "./model-runtime-client";

export type {
  CapabilityState,
  HealthRow,
  PricingKind,
  RuntimeHealthView,
  RuntimeModelView,
  RuntimeProviderView,
  RuntimeRouteCandidateView,
  RuntimeRouteDecisionView,
  RuntimeRoutingView,
  RuntimeUsageView,
  RouteQuery,
} from "./model-runtime-client";

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function listRuntimeProviders(): Promise<RuntimeProviderView[]> {
  const body = await api<{ providers: RuntimeProviderView[] }>("/api/harness/model-runtime/providers");
  return body.providers ?? [];
}

export async function listRuntimeModels(provider?: string): Promise<RuntimeModelView[]> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  const body = await api<{ models: RuntimeModelView[] }>(`/api/harness/model-runtime/models${query}`);
  return body.models ?? [];
}

export async function getRuntimeRouting(): Promise<RuntimeRoutingView> {
  return api<RuntimeRoutingView>("/api/harness/model-runtime/routing");
}

export async function getRuntimeDecisions(limit = 20): Promise<RuntimeRouteDecisionView[]> {
  const body = await api<{ decisions: RuntimeRouteDecisionView[] }>(
    `/api/harness/model-runtime/routing/decisions?limit=${limit}`,
  );
  return body.decisions ?? [];
}

export async function routeModel(query: RouteQuery): Promise<RuntimeRouteDecisionView> {
  const body = await api<{ decision: RuntimeRouteDecisionView }>("/api/harness/model-runtime/route", {
    method: "POST",
    body: JSON.stringify(query),
  });
  return body.decision;
}

export async function getRuntimeHealth(): Promise<RuntimeHealthView> {
  return api<RuntimeHealthView>("/api/harness/model-runtime/health");
}

export async function getRuntimeUsage(): Promise<RuntimeUsageView> {
  return api<RuntimeUsageView>("/api/harness/model-runtime/usage");
}

// ── Pure, client-safe render helpers ────────────────────────────────────────

/** The plain status key for a capability state. The ONE place the word is chosen. */
export function capabilityStateKey(state: CapabilityState): string {
  return `modelRuntime.capability.${state}`;
}

/** Health bucket from a 0..1 ratio, or null when there is no evidence yet. */
export function healthBucket(health: number | null | undefined): "good" | "watch" | "bad" | "unknown" {
  if (health === null || health === undefined) return "unknown";
  if (health >= 0.95) return "good";
  if (health >= 0.8) return "watch";
  return "bad";
}

/** Human-readable pricing sentence key. Unknown stays unknown, never "$0". */
export function pricingKey(kind: PricingKind): string {
  return `modelRuntime.pricing.${kind}`;
}

/**
 * Translate a key the runtime supplied dynamically (a task name, a capability
 * state, a circuit state). The i18n layer types keys as literals, but these
 * keys come from data, so the cast is confined to this one helper.
 */
export function dynKey(t: (key: never, vars?: never) => string, key: string): string {
  return (t as unknown as (k: string) => string)(key);
}
