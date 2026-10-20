// Generated-capability browser client.
// Reads the durable records the Capability Builder wrote and performs the
// operator's activate / deactivate / rollback / retire actions. The server
// re-checks operator authorization; the client never grants anything itself.

export type CapabilityStatus =
  | "draft"
  | "unverified"
  | "tested"
  | "approval_required"
  | "active"
  | "disabled"
  | "retired";

export interface CapabilityManifestPort {
  name: string;
  kind: string;
  required?: boolean;
  description?: string;
}

export interface CapabilityManifest {
  id: string;
  version: string;
  kind: string;
  title: string;
  description: string;
  scope: string;
  inputs: CapabilityManifestPort[];
  outputs: CapabilityManifestPort[];
  permissions: string[];
  effect: string;
  timeoutMs: number;
  imports: string[];
  tests: string[];
  acceptance: string;
}

export interface CapabilityUsageSummary {
  total: number;
  ok: number;
  failed: number;
  lastStatus: string | null;
  lastUsedAt: string | null;
}

export interface CapabilityRecord {
  id: string;
  capabilityId: string;
  version: string;
  kind: string;
  title: string;
  description: string;
  scope: string;
  status: CapabilityStatus;
  manifest: CapabilityManifest | Record<string, unknown>;
  sourceDigest: string;
  testDigest: string;
  testStatus: string;
  tests: string[];
  dir: string;
  runId?: string | null;
  createdAt: string;
  updatedAt: string;
  usage?: CapabilityUsageSummary;
}

export interface CapabilityListResult {
  capabilities: CapabilityRecord[];
  count: number;
}

export interface BuiltinCapabilityInput {
  name: string;
  kind: string;
  description: string;
  required?: boolean;
}

export interface BuiltinCapability {
  id: string;
  name: string;
  title: string;
  description: string;
  kind: string;
  source: 'builtin';
  inputs: BuiltinCapabilityInput[];
}

export interface BuiltinListResult {
  builtins: BuiltinCapability[];
  count: number;
}

export interface CapabilityMutationResult {
  success: boolean;
  result: Record<string, unknown>;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

function mutation(path: string, body: Record<string, unknown> = {}): Promise<CapabilityMutationResult> {
  return api<CapabilityMutationResult>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listCapabilities(status?: CapabilityStatus): Promise<CapabilityListResult> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await api<{ capabilities?: CapabilityRecord[]; count?: number }>(
    `/api/capabilities${query}`,
  );
  return { capabilities: body.capabilities ?? [], count: body.count ?? 0 };
}

export async function listBuiltins(): Promise<BuiltinListResult> {
  const body = await api<{ builtins?: BuiltinCapability[]; count?: number }>(
    '/api/capabilities/builtins',
  );
  return { builtins: body.builtins ?? [], count: body.count ?? 0 };
}

export async function getCapability(capabilityId: string): Promise<CapabilityRecord[]> {
  const body = await api<{ versions?: CapabilityRecord[] }>(
    `/api/capabilities/${encodeURIComponent(capabilityId)}`,
  );
  return body.versions ?? [];
}

export function activateCapability(capabilityId: string, version?: string) {
  return mutation(`/api/capabilities/${encodeURIComponent(capabilityId)}/activate`, { version });
}

export function deactivateCapability(capabilityId: string, version?: string) {
  return mutation(`/api/capabilities/${encodeURIComponent(capabilityId)}/deactivate`, { version });
}

export function promoteCapability(capabilityId: string, version?: string) {
  return mutation(`/api/capabilities/${encodeURIComponent(capabilityId)}/promote`, { version });
}

export function rollbackCapability(capabilityId: string, version?: string) {
  return mutation(`/api/capabilities/${encodeURIComponent(capabilityId)}/rollback`, { version });
}

export function removeCapability(capabilityId: string) {
  return mutation(`/api/capabilities/${encodeURIComponent(capabilityId)}/remove`);
}
