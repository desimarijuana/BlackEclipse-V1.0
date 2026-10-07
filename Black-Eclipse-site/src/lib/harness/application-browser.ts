// ─── Application Runtime browser client ──────────────────────────────────────
// The UI talks to the Next.js proxy (`/api/runtime/**`), which forwards to the
// Python runtime. MUST stay client-safe: fetch only, no prisma, no child_process,
// no fs, no runtime secret. The server owns runtime state.

export interface ApplicationDescriptorView {
  name: string;
  language: string;
  framework: string;
  runtime: string;
  packageManager: string;
  lockfile: string;
  docker: boolean;
  compose: boolean;
  services: string[];
  ports: number[];
  requiredEnv: string[];
  commands: Record<string, string>;
}

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
}

export interface RuntimeView {
  runtimeId: string;
  applicationId: string;
  state: string;
  descriptor: ApplicationDescriptorView | null;
  serviceGraph: { nodes: ServiceNodeView[]; startupOrder: string[] } | null;
  services: string[];
  ports: Array<{ port: number; service: string; likelyService: string }>;
  processes: string[];
  containers: string[];
  health: { status: string; healthy: boolean; reason: string };
  restartCount: number;
  lastError: { category?: string; message?: string } | null;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body.error ?? `request failed (${res.status})`);
  return body;
}

export function listRuntimes(): Promise<RuntimeView[]> {
  return api<{ runtimes: RuntimeView[] }>("/api/runtime/list").then((b) => b.runtimes ?? []);
}

export function inspectApplication(): Promise<{ descriptor: ApplicationDescriptorView; serviceGraph: unknown }> {
  return api("/api/runtime/inspect");
}

export function startApplication(body: Record<string, unknown> = {}): Promise<{ runtime: RuntimeView }> {
  return api("/api/runtime/start", { method: "POST", body: JSON.stringify(body) });
}

export function stopApplication(runtimeId: string): Promise<unknown> {
  return api(`/api/runtime/${encodeURIComponent(runtimeId)}/stop`, { method: "POST" });
}

export function restartApplication(runtimeId: string): Promise<{ runtime: RuntimeView }> {
  return api(`/api/runtime/${encodeURIComponent(runtimeId)}/restart`, { method: "POST" });
}

export function runtimeLogs(runtimeId: string, tail = 200): Promise<{ streams: Array<{ processId: string; text: string }> }> {
  return api(`/api/runtime/${encodeURIComponent(runtimeId)}/logs?tail=${tail}`);
}

export function diagnoseRuntime(runtimeId: string): Promise<{ diagnosis: { category: string; message: string; suggestedActions: string[] } }> {
  return api(`/api/runtime/${encodeURIComponent(runtimeId)}/diagnose`);
}

export function recoverRuntime(runtimeId: string): Promise<unknown> {
  return api(`/api/runtime/${encodeURIComponent(runtimeId)}/recover`, { method: "POST", body: JSON.stringify({}) });
}

export interface AdapterView {
  name: string;
  available: boolean;
  capabilities?: string[];
  operations?: string[];
}

export function listAdapters(): Promise<{
  orchestrators: AdapterView[];
  infrastructure: AdapterView[];
  cloudProviders: AdapterView[];
}> {
  return api("/api/runtime/orchestrators");
}
