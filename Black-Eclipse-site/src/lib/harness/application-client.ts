// ─── Application Runtime front door (server) ─────────────────────────────────
// A thin, typed proxy over the Python runtime's /runtime routes. Like
// terminal-client.ts it adds NO runtime logic: it forwards with the operator token
// and returns what the runtime reports. The application runtime is shared by the
// agent tools and this UI, so there is one source of truth for runtimes/services.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export interface ServiceNodeView {
  name: string;
  kind: string;
  image: string;
  containerId: string;
  processId: string;
  ports: number[];
  dependsOn: string[];
  state: string;
  health: string;
  compose: boolean;
  notes: string;
}

export interface RuntimePortView {
  port: number;
  host: string;
  purpose: string;
  source: string;
  service: string;
  pid: number | null;
  processId: string | null;
  likelyService: string;
}

export interface HealthCheckView {
  check: string;
  kind: string;
  status: string;
  ok: boolean;
  detail: string;
  attempts: number;
  latencyMs: number;
}

export interface RuntimeHealthView {
  status: string;
  healthy: boolean;
  checks: HealthCheckView[];
  reason: string;
}

export interface DescriptorView {
  name: string;
  path: string;
  language: string;
  framework: string;
  runtime: string;
  packageManager: string;
  docker: boolean;
  compose: boolean;
  composeFile: string;
  services: string[];
  ports: number[];
  requiredEnv: string[];
}

export interface RuntimeView {
  runtimeId: string;
  applicationId: string;
  state: string;
  descriptor: DescriptorView | null;
  serviceGraph: { nodes: ServiceNodeView[]; edges: Array<{ from: string; to: string }>; startupOrder: string[] } | null;
  services: string[];
  ports: RuntimePortView[];
  processes: string[];
  containers: string[];
  health: RuntimeHealthView;
  startedAt: number;
  restartCount: number;
  lastError: { category?: string; message?: string } | null;
}

export async function requestRuntime<T>(path: string, init: RequestInit = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}/runtime${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(init.headers ?? {}),
    },
    signal: init.signal ?? AbortSignal.timeout(900_000),
  });
  const payload = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new Error(redactSecrets(payload.error ?? `runtime request failed (${res.status})`));
  }
  return payload;
}

export function runtimeDescribe() {
  return requestRuntime<{ runtimes: unknown; capabilities: unknown }>("/status");
}

export function runtimeList(): Promise<RuntimeView[]> {
  return requestRuntime<{ runtimes: RuntimeView[] }>("/list").then((b) => b.runtimes ?? []);
}

export function runtimeDetect(): Promise<Record<string, unknown>> {
  return requestRuntime("/detect");
}

export function runtimeInspect(): Promise<Record<string, unknown>> {
  return requestRuntime("/inspect");
}

export function runtimeStart(body: Record<string, unknown> = {}): Promise<{ runtime: RuntimeView }> {
  return requestRuntime("/start", { method: "POST", body: JSON.stringify(body) });
}

export function runtimeStop(runtimeId: string): Promise<unknown> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/stop`, { method: "POST" });
}

export function runtimeRestart(runtimeId: string): Promise<{ runtime: RuntimeView }> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/restart`, { method: "POST" });
}

export function runtimeCleanup(runtimeId: string): Promise<unknown> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/cleanup`, { method: "POST" });
}

export function runtimeLogs(runtimeId: string, tail = 200): Promise<{ streams: Array<{ processId: string; text: string }> }> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/logs?tail=${tail}`);
}

export function runtimeDiagnose(runtimeId: string): Promise<{ diagnosis: { category: string; message: string; suggestedActions: string[] } }> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/diagnose`);
}

export function runtimeRecover(runtimeId: string, maxAttempts?: number): Promise<unknown> {
  return requestRuntime(`/${encodeURIComponent(runtimeId)}/recover`, {
    method: "POST",
    body: JSON.stringify({ maxAttempts }),
  });
}

export function runtimeReconcile(): Promise<unknown> {
  return requestRuntime("/reconcile", { method: "POST" });
}

// ── orchestration / infrastructure / cloud ──────────────────────────────────

export interface AdapterView {
  name: string;
  available: boolean;
  version?: string;
  capabilities?: string[];
  operations?: string[];
}

export function listAdapters(): Promise<{
  orchestrators: AdapterView[];
  infrastructure: AdapterView[];
  cloudProviders: AdapterView[];
}> {
  return requestRuntime("/orchestrators");
}

export function runOrchestrator(
  operation: string,
  args: Record<string, unknown> = {},
  opts: { adapter?: string; authorized?: boolean } = {},
): Promise<{ success: boolean; result: unknown }> {
  return requestRuntime(`/orchestrator/${encodeURIComponent(operation)}`, {
    method: "POST",
    body: JSON.stringify({ adapter: opts.adapter ?? "", args, authorized: opts.authorized ?? false }),
  });
}

export function runTerraform(
  operation: string,
  args: Record<string, unknown> = {},
  opts: { adapter?: string; authorized?: boolean } = {},
): Promise<{ success: boolean; result: unknown }> {
  return requestRuntime(`/terraform/${encodeURIComponent(operation)}`, {
    method: "POST",
    body: JSON.stringify({ adapter: opts.adapter ?? "", args, authorized: opts.authorized ?? false }),
  });
}

export function runDeploy(body: Record<string, unknown>): Promise<{ success: boolean; deployment: unknown }> {
  return requestRuntime("/deploy", { method: "POST", body: JSON.stringify(body) });
}

export function providerReadiness(): Promise<unknown> {
  return requestRuntime("/providers");
}

export function workspaceGraphApi(): Promise<unknown> {
  return requestRuntime("/workspace/graph");
}
