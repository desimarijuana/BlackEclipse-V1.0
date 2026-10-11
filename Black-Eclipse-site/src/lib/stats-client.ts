// Statistical Analysis Engine client — thin front-door proxy to the Python
// `/stats/v1/*` operator routes. No state, no store; the runtime owns all
// computation.

const BASE = "/api/stats";

export type StatsToolCategory =
  | "returns" | "volatility" | "relationships" | "risk" | "inference"
  | "regression" | "regime" | "features" | "anomaly" | "factor";

export interface StatsResponse {
  status: "ok" | "error";
  tool: string;
  toolVersion: string;
  parameters: Record<string, unknown>;
  summary: Record<string, unknown>;
  results: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  warnings: string[];
  errors: { code: string; message: string }[];
  provenance: Record<string, unknown>;
  executionMetadata: Record<string, unknown>;
  artifactReferences: unknown[];
}

export interface StatsTool {
  name: string;
  category: StatsToolCategory;
  description: string;
  inputSchema: Record<string, unknown>;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path ? `/${path}` : ""}`, { cache: "no-store" });
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path ? `/${path}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    return { status: "error", tool: path, errors: [payload?.detail ?? { code: "HTTP_ERROR", message: String(res.status) }] } as T;
  }
  return (await res.json()) as T;
}

export function fetchStatsCapabilities(): Promise<{ available: boolean; tools: string[] }> {
  return getJson("capabilities");
}

export function fetchStatsTools(): Promise<{ tools: StatsTool[] }> {
  return getJson("tools");
}

export function runStatsTool(tool: string, args: Record<string, unknown>): Promise<StatsResponse> {
  return postJson<StatsResponse>(tool, args);
}

export function executeStats(tool: string, args: Record<string, unknown>): Promise<StatsResponse> {
  return postJson<StatsResponse>("execute", { tool, arguments: args });
}
