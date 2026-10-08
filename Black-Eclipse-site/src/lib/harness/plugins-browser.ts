// ─── Plugin Platform browser front door ──────────────────────────────────────
// A thin, typed client over the Next proxy (`/api/harness/plugins/*`), which in
// turn reaches the Python plugin manager. It adds NO plugin logic: it validates
// shapes and returns what the runtime owns. Browser-safe (no child_process, no
// server-only imports) — the screen imports THIS, never the harness server code.

const BASE = "/api/harness/plugins";

export interface PluginRecord {
  pluginId: string;
  name: string;
  version: string;
  publisher: string;
  status: string;
  enabled: boolean;
  trust: string;
  installationPath: string;
  permissions: string[];
  verification: string;
  health: string;
  lastError: string | null;
  manifest: Record<string, unknown>;
}

export interface PluginSummary {
  installed: number;
  enabled: number;
  errors?: number;
  tools?: number;
  secretsAvailable?: boolean;
}

export interface PluginContribution {
  pluginId?: string;
  kind: string;
  name: string;
  meta?: Record<string, unknown>;
  namespaced?: string;
}

export interface PluginHealth {
  pluginId: string;
  status: string;
  state: string | null;
  toolCalls: number;
  toolFailures: number;
  eventFailures: number;
  hookFailures: number;
  httpFailures: number;
  crashes: number;
  restarts: number;
  latencyMs: number;
  lastError: string | null;
}

export interface PluginInspect {
  plugin: PluginRecord;
  health: PluginHealth;
  contributions: PluginContribution[];
  config: { fields: ConfigFieldView[] };
  secrets: string[];
  dependencies: { id: string; version: string; satisfied: boolean }[];
}

export interface ConfigFieldView {
  key: string;
  type: string;
  title: string;
  description?: string;
  required?: boolean;
  enum?: unknown[];
  set: boolean;
  value: unknown;
}

export interface UiPanel {
  id: string;
  title: string;
  kind: string;
}

export type PluginView =
  | { type: "markdown"; body: string }
  | { type: "keyvalue"; items: { label: string; value: unknown }[] }
  | { type: "table"; columns: string[]; rows: unknown[][] }
  | { type: "list"; items: unknown[] }
  | { type: "status"; status: string; detail?: string }
  | { type: "empty"; body: string };

export interface PluginPanelView {
  pluginId: string;
  panelId: string;
  view: PluginView;
}

export interface RegistryEntry {
  id: string;
  name: string;
  version: string;
  description: string;
  publisher: string;
  category: string;
  tags: string[];
  permissions: string[];
  verified: string;
  trust: string;
}

export interface WebhookTarget {
  webhook: string;
  direction: string;
  url: string | null;
  signed: boolean;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string" ? detail : detail?.message ?? data?.error ?? `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

export function listPlugins(): Promise<{ plugins: PluginRecord[]; summary: PluginSummary }> {
  return api("/");
}

export function getPlugin(id: string): Promise<PluginInspect> {
  return api(`/${encodeURIComponent(id)}`);
}

export function pluginHealth(id: string): Promise<PluginHealth> {
  return api(`/${encodeURIComponent(id)}/health`);
}

export function pluginDoctor(id: string): Promise<Record<string, unknown>> {
  return api(`/${encodeURIComponent(id)}/doctor`);
}

export function uiPanels(id: string): Promise<{ panels: UiPanel[] }> {
  return api(`/${encodeURIComponent(id)}/ui`);
}

export function renderPanel(id: string, panelId: string): Promise<PluginPanelView> {
  return api(`/${encodeURIComponent(id)}/ui/${encodeURIComponent(panelId)}`);
}

export function availablePlugins(): Promise<{ plugins: RegistryEntry[] }> {
  return api("/available");
}

export function registrySearch(query: string): Promise<{ results: RegistryEntry[] }> {
  const q = new URLSearchParams({ q: query }).toString();
  return api(`/registry/search?${q}`);
}

export function enablePlugin(id: string): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}/enable`, { method: "POST", body: "{}" });
}

export function disablePlugin(id: string): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}/disable`, { method: "POST", body: "{}" });
}

export function uninstallPlugin(id: string): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function installPlugin(source: string, enable = false): Promise<unknown> {
  return api("/install", { method: "POST", body: JSON.stringify({ source, enable }) });
}

export function registryInstall(pluginId: string, enable = false): Promise<unknown> {
  return api("/registry/install", { method: "POST", body: JSON.stringify({ pluginId, enable }) });
}

export function setPluginConfig(id: string, values: Record<string, unknown>): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}/config`, { method: "PUT", body: JSON.stringify({ values }) });
}

export function setPluginSecret(id: string, name: string, value: string): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}/secrets`, { method: "POST", body: JSON.stringify({ name, value }) });
}

export function authStart(id: string): Promise<Record<string, unknown>> {
  return api(`/${encodeURIComponent(id)}/oauth/start`, { method: "POST", body: "{}" });
}

export function authStatus(id: string): Promise<Record<string, unknown>> {
  return api(`/${encodeURIComponent(id)}/auth`);
}

export function authLogout(id: string): Promise<unknown> {
  return api(`/${encodeURIComponent(id)}/oauth`, { method: "DELETE" });
}

export function webhookTargets(id: string): Promise<{ webhooks: WebhookTarget[] }> {
  return api(`/${encodeURIComponent(id)}/webhooks`);
}
