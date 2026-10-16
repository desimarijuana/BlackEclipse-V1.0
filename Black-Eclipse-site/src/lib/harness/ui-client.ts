// ─── UI Engineering BROWSER client ───────────────────────────────────────────
// The UI Builder and preview screens talk to the Next.js API routes
// (`/api/ui/**`), which proxy to the Python runtime. This module MUST stay
// client-safe: no Node built-ins, no server-only helpers. Fetch only.
//
// The wire contract is the Python runtime's camelCase form; it mirrors
// `src/lib/ui-engineering/` (the pure TS foundation) so a blueprint produced
// here validates and renders identically in the browser.

export type ComponentAvailability = "available" | "unavailable";
export type OwnershipKind = "core" | "plugin" | "user";
export type BlueprintKind = "page" | "workspace";
export type BlueprintScope = "personal" | "shared";
export type ChangeType =
  | "add_widget" | "remove_widget" | "move_widget" | "resize_widget"
  | "config_changed" | "meta_changed" | "layout_changed";

export interface ConfigFieldSpec {
  key: string;
  label: string;
  kind: "text" | "number" | "select" | "boolean" | "symbol" | "symbols";
  options: { value: string; label: string }[];
  required: boolean;
  default: unknown;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  placeholder?: string | null;
}

export interface UiComponentSpec {
  id: string;
  version: string;
  displayName: string;
  description: string;
  category: string;
  icon: string;
  tags: string[];
  configSchema: ConfigFieldSpec[];
  defaultConfig: Record<string, unknown>;
  dataSources: string[];
  actions: string[];
  layout: { sizes: string[]; minHeight?: number | null; defaultHeight?: number | null; resizable: boolean; zones: string[] };
  availability: ComponentAvailability;
  owner: OwnershipKind;
  pluginId?: string | null;
}

export interface WidgetPlacement {
  id: string;
  widgetId: string;
  height: number | null;
  defaultHeight?: number | null;
  minHeight?: number | null;
  config?: Record<string, unknown> | null;
  hidden?: boolean | null;
}

export interface WorkspaceColumn { id: string; weight: number; widgets: WidgetPlacement[] }
export interface WorkspaceSection { id: string; zone?: string | null; columns: WorkspaceColumn[] }
export interface WorkspaceLayout {
  version: number;
  sections: WorkspaceSection[];
  hiddenZones?: string[] | null;
  zoneWidths?: Record<string, number> | null;
}

export interface UiBlueprint {
  schemaVersion: number;
  id: string;
  title: string;
  description?: string | null;
  kind: BlueprintKind;
  owner: { kind: OwnershipKind; id: string };
  scope: BlueprintScope;
  path?: string | null;
  icon?: string | null;
  tags?: string[] | null;
  layout: WorkspaceLayout;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface BlueprintSummary {
  id: string;
  title: string;
  kind: BlueprintKind;
  scope: BlueprintScope;
  ownerId: string;
  path?: string | null;
  icon?: string | null;
  revision: number;
  updatedAt: string;
  widgetCount: number;
  componentIds: string[];
}

export interface CurrentPageResolution {
  resolution: "explicit_id" | "path" | "title" | "title_ambiguous" | "default_most_recent";
  candidates: { id: string; title: string; path?: string | null; updatedAt: string }[];
}

export interface BlueprintChange {
  type: ChangeType;
  instanceId?: string | null;
  componentId?: string | null;
  detail: string;
}

export interface UiInstance {
  instanceId: string;
  componentId: string;
  category: string | null;
  owner: OwnershipKind | null;
  availability: ComponentAvailability | "unavailable";
  config: Record<string, unknown>;
  hidden: boolean;
  sectionId: string;
  columnId: string;
  height: number | null;
}

export interface DropTarget {
  sectionId: string;
  columnId?: string | null;
  index?: number;
  columnIndex?: number | null;
}

interface UiEnvelope { success?: boolean; error?: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/ui${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const data = (await res.json().catch(() => ({}))) as T & UiEnvelope;
  if (!res.ok) throw new Error(data.error || `ui request failed (${res.status})`);
  return data;
}

export function getApplicationMap() {
  return req<{ pageCount: number; pages: BlueprintSummary[]; capabilities: UiCapabilities }>("/application-map");
}
export function getCapabilities() {
  return req<UiCapabilities>("/capabilities");
}
export function classifyRequest(text: string, blueprintId?: string) {
  return req<{ mode: "compose" | "engineer" | "both"; reasons: string[]; suggestedTools: string[]; confidence: number; matchedComponents: string[] }>("/classify", { method: "POST", body: JSON.stringify({ text, blueprintId }) });
}
export function startEngineering(text: string, blueprintId?: string) {
  return req<{ created: boolean; mode: string; planId?: string; taskId?: string; acceptance?: string[]; message?: string }>("/engineering", { method: "POST", body: JSON.stringify({ text, blueprintId }) });
}
export function engineeringStatus(planId: string) {
  return req<{ plan: { plan: { id: string; status: string }; tasks: unknown[] } }>(`/engineering/${encodeURIComponent(planId)}`);
}
export function listComponents(query: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") qs.set(k, String(v));
  return req<{ components: UiComponentSpec[] }>(`/components?${qs.toString()}`);
}
export function inspectComponent(componentId: string) {
  return req<{ component: UiComponentSpec }>(`/components/${encodeURIComponent(componentId)}`);
}
export function registerComponent(spec: unknown) {
  return req<{ component: UiComponentSpec }>("/components", { method: "POST", body: JSON.stringify({ spec }) });
}

export function listBlueprints(query: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") qs.set(k, String(v));
  return req<{ blueprints: BlueprintSummary[]; total: number }>(`/blueprints?${qs.toString()}`);
}
export function createPage(input: { title: string; description?: string; kind?: BlueprintKind; scope?: BlueprintScope; path?: string; icon?: string; tags?: string[]; idempotencyKey?: string }) {
  return req<{ blueprint: UiBlueprint }>("/blueprints", { method: "POST", body: JSON.stringify(input) });
}
export function getBlueprint(blueprintId: string) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}`);
}
export function updatePage(blueprintId: string, patch: { title?: string; description?: string; path?: string; icon?: string; tags?: string[] }) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}`, { method: "PATCH", body: JSON.stringify(patch) });
}
export function deleteBlueprint(blueprintId: string) {
  return req<{ removed: boolean }>(`/blueprints/${encodeURIComponent(blueprintId)}`, { method: "DELETE" });
}
export function duplicatePage(blueprintId: string, title?: string) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/duplicate`, { method: "POST", body: JSON.stringify({ title }) });
}
export function getCurrentPage(blueprintId: string) {
  return req<{ blueprint: UiBlueprint; revision: number; instances: UiInstance[]; resolution: "explicit_id"; candidates: [] }>(`/blueprints/${encodeURIComponent(blueprintId)}/current`);
}
export function resolveCurrentPage(input: { blueprintId?: string; path?: string; title?: string } = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(input)) if (v) qs.set(k, v);
  return req<{ blueprint: UiBlueprint; revision: number; instances: UiInstance[] } & CurrentPageResolution>(`/current-page?${qs.toString()}`);
}
export function getLayout(blueprintId: string) {
  return req<{ blueprintId: string; revision: number; layout: WorkspaceLayout }>(`/blueprints/${encodeURIComponent(blueprintId)}/layout`);
}
export function saveLayout(blueprintId: string, layout: WorkspaceLayout, expectedRevision?: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/layout`, { method: "PUT", body: JSON.stringify({ layout, expectedRevision }) });
}
export function getHistory(blueprintId: string) {
  return req<{ blueprintId: string; revisions: { revision: number; summary: string; changes: BlueprintChange[]; createdAt: string }[] }>(`/blueprints/${encodeURIComponent(blueprintId)}/history`);
}
export function exportBlueprint(blueprintId: string) {
  return req<{ kind: string; schemaVersion: number; exportedAt: string; blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/export`);
}
export function importBlueprint(payload: unknown) {
  const blueprint = (payload as { blueprint?: unknown })?.blueprint ?? payload;
  return req<{ blueprint: UiBlueprint }>("/blueprints/import", { method: "POST", body: JSON.stringify({ blueprint }) });
}
export function restoreRevision(blueprintId: string, revision: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/restore`, { method: "POST", body: JSON.stringify({ revision }) });
}
export function previewChange(blueprintId: string, ops: Record<string, unknown>[]) {
  return req<{ blueprint: UiBlueprint; changes: BlueprintChange[]; currentRevision: number; nextRevision: number }>(`/blueprints/${encodeURIComponent(blueprintId)}/preview`, { method: "POST", body: JSON.stringify({ ops }) });
}

export function addWidget(blueprintId: string, input: { componentId: string; instanceId?: string; target?: DropTarget; config?: Record<string, unknown>; zone?: string; height?: number; expectedRevision?: number }) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets`, { method: "POST", body: JSON.stringify(input) });
}
export function removeWidget(blueprintId: string, instanceId: string) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets/${encodeURIComponent(instanceId)}`, { method: "DELETE" });
}
export function moveWidget(blueprintId: string, instanceId: string, target: DropTarget, expectedRevision?: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets/${encodeURIComponent(instanceId)}/move`, { method: "POST", body: JSON.stringify({ target, expectedRevision }) });
}
export function reorderWidget(blueprintId: string, instanceId: string, toIndex: number, expectedRevision?: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets/${encodeURIComponent(instanceId)}/reorder`, { method: "POST", body: JSON.stringify({ toIndex, expectedRevision }) });
}
export function resizeWidget(blueprintId: string, instanceId: string, height: number | null, expectedRevision?: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets/${encodeURIComponent(instanceId)}/resize`, { method: "POST", body: JSON.stringify({ height, expectedRevision }) });
}
export function updateWidgetConfig(blueprintId: string, instanceId: string, patch: Record<string, unknown>, expectedRevision?: number) {
  return req<{ blueprint: UiBlueprint }>(`/blueprints/${encodeURIComponent(blueprintId)}/widgets/${encodeURIComponent(instanceId)}/config`, { method: "POST", body: JSON.stringify({ patch, expectedRevision }) });
}

export function getOperation(operationId: string) {
  return req<{ operation: { id: string; operation: string; status: string; blueprintId?: string | null; detail: string; error?: string | null; createdAt: string } }>(`/operations/${encodeURIComponent(operationId)}`);
}

export interface UiCapabilities {
  componentCount: number;
  categories: string[];
  dataSources: string[];
  components: string[];
}
