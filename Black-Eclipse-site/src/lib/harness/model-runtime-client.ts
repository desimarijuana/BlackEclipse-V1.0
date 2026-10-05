// ─── Model Runtime front door (server) ──────────────────────────────────────
// Thin, typed proxy over the Python runtime's `/model-runtime/*` routes. Adds no
// model logic of its own: it validates, forwards, and returns what the runtime
// owns. Operator-gated routes present the runtime secret by transport/token,
// never a body boolean. Credentials are never returned by any route here.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type CapabilityState = "supported" | "unsupported" | "unknown" | "degraded";
export type PricingKind = "per_token" | "per_request" | "free" | "unknown" | "custom";

export interface RuntimeProviderView {
  id: string;
  label: string;
  kind: string;
  enabled: boolean;
  keyless: boolean;
  openaiCompatible: boolean;
  defaultBaseUrl: string | null;
  dynamicDiscovery: boolean;
  metadata: Record<string, unknown>;
}

export interface RuntimeModelView {
  id: string;
  providerId: string;
  qualifiedId: string;
  displayName: string;
  capabilities: {
    states: Record<string, CapabilityState>;
    supported: string[];
    degraded: string[];
    unsupported: string[];
    unknown: string[];
  };
  contextWindow: number | null;
  maxOutputTokens: number | null;
  pricing: {
    kind: PricingKind;
    inputPerMillion: number | null;
    outputPerMillion: number | null;
    cachedInputPerMillion: number | null;
    perRequest: number | null;
    currency: string;
    source: string | null;
  };
  performance: Record<string, number | null>;
  status: "active" | "deprecated" | "unavailable";
  aliases: string[];
  metadata: Record<string, unknown>;
}

export interface RuntimeRouteCandidateView {
  model: string;
  provider: string;
  score: number | null;
  breakdown: Record<string, number>;
  excludedReason: string | null;
}

export interface RuntimeRouteDecisionView {
  requestId: string;
  task: string;
  alias: string | null;
  reason: string;
  requirements: Record<string, unknown>;
  selected: RuntimeRouteCandidateView | null;
  fallbacks: RuntimeRouteCandidateView[];
  candidates: RuntimeRouteCandidateView[];
  policy: Record<string, unknown>;
}

export interface RuntimeUsageView {
  requests: number;
  successful: number;
  failed: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCost: number;
  averageLatencyMs: number | null;
  cost?: number;
  budgets?: Array<Record<string, unknown>>;
  persisted?: {
    recentRequests: Array<Record<string, unknown>>;
    health: Array<Record<string, unknown>>;
  };
}

export interface RuntimeHealthView {
  providers: HealthRow[];
}

/** One provider's health row. Absent values mean "not measured yet". */
export interface HealthRow {
  id: string;
  label?: string;
  enabled?: boolean;
  circuit?: string;
  count?: number;
  health?: number | null;
  errorRate?: number | null;
  latency?: { p50?: number | null; p90?: number | null; p95?: number | null; p99?: number | null };
  toolSuccessRate?: number | null;
  structuredOutputSuccessRate?: number | null;
  rateLimit?: Record<string, unknown>;
}

export interface RuntimeRoutingView {
  taskProfiles: string[];
  aliases: string[];
  policy: Record<string, unknown>;
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  if (!(await ensurePythonRuntime())) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 30_000, ...rest } = init;
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

export async function listRuntimeProviders(): Promise<RuntimeProviderView[]> {
  const body = await request<{ providers: RuntimeProviderView[] }>("/model-runtime/providers", { method: "GET" });
  return body.providers ?? [];
}

export async function listRuntimeModels(provider?: string): Promise<RuntimeModelView[]> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  const body = await request<{ models: RuntimeModelView[] }>(`/model-runtime/models${query}`, { method: "GET" });
  return body.models ?? [];
}

export interface DiscoveryResult {
  ok: boolean;
  detail: string | null;
  models: RuntimeModelView[];
  /**
   * The provider's OWN served model ids, before the registry merge. This is the
   * authoritative "what is installed" signal — `models` also contains declared
   * catalog placeholders that may not exist on the server.
   */
  served: string[];
}

/**
 * Probe a live provider for the models it actually serves and register them.
 * A local server (Ollama, LM Studio) lists its installed models; a router lists
 * its catalog. The connection details are supplied per call (the runtime cannot
 * read the vault) and are never persisted. A failed probe reports `ok: false`
 * with a reason — never a silent empty success.
 */
export async function discoverRuntimeModels(
  providerId: string,
  connection: { baseUrl?: string | null; apiKey?: string | null; model?: string | null },
): Promise<DiscoveryResult> {
  const body = await request<{
    ok: boolean;
    detail?: string | null;
    models: RuntimeModelView[];
    served?: string[];
  }>(
    `/model-runtime/providers/${encodeURIComponent(providerId)}/discover`,
    {
      method: "POST",
      body: JSON.stringify({
        baseUrl: connection.baseUrl ?? undefined,
        apiKey: connection.apiKey ?? undefined,
        model: connection.model ?? undefined,
      }),
      timeoutMs: 20_000,
    },
  );
  return {
    ok: Boolean(body.ok),
    detail: body.detail ?? null,
    models: body.models ?? [],
    served: Array.isArray(body.served) ? body.served.filter((m) => typeof m === "string" && m) : [],
  };
}

export async function getRuntimeRouting(): Promise<RuntimeRoutingView> {
  return request<RuntimeRoutingView>("/model-runtime/routing", { method: "GET" });
}

export async function getRuntimeDecisions(limit = 20): Promise<RuntimeRouteDecisionView[]> {
  const body = await request<{ decisions: RuntimeRouteDecisionView[] }>(
    `/model-runtime/routing/decisions?limit=${limit}`,
    { method: "GET" },
  );
  return body.decisions ?? [];
}

export interface RouteQuery {
  model?: string;
  task?: string;
  requirements?: Record<string, unknown>;
  policy?: Record<string, unknown>;
}

export async function routeModel(query: RouteQuery): Promise<RuntimeRouteDecisionView> {
  const body = await request<{ decision: RuntimeRouteDecisionView }>("/model-runtime/route", {
    method: "POST",
    body: JSON.stringify(query),
  });
  return body.decision;
}

export async function getRuntimeHealth(): Promise<RuntimeHealthView> {
  return request<RuntimeHealthView>("/model-runtime/health", { method: "GET" });
}

export async function getRuntimeUsage(): Promise<RuntimeUsageView> {
  return request<RuntimeUsageView>("/model-runtime/usage", { method: "GET" });
}
