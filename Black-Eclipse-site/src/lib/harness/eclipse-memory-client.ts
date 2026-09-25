// ─── Eclipse-Memory server client (front door) ──────────────────────────────
// Thin typed wrapper over the Python runtime's /eclipse-memory endpoints. It
// adds no memory logic. The browser MUST NOT import this file (it pulls the
// Python client); use `eclipse-memory-browser.ts`.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";
import type {
  CorrectionRecord,
  EclipseMemoryHealth,
  MemoryDatabaseHealth,
  MemoryDetail,
  MemoryExportDocument,
  MemoryLifecycleResponse,
  MemoryOverview,
  MemoryRecord,
  MemoryRetentionStatus,
  MemoryRetrievalDiagnostics,
  MemorySemanticStatus,
  MistakeRecord,
} from "./eclipse-memory-types";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 30_000, ...rest } = init;
  // The Python runtime authorizes operator mutations by transport (loopback) or
  // by this secret — never by a body boolean. Forwarding it means the front
  // door's own authorization is what reaches Python, even if the runtime is
  // later bound to a non-loopback interface. The value is never logged.
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
    const detail = (body as { detail?: string; error?: string }).detail
      || (body as { error?: string }).error
      || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function memoryHealth(): Promise<EclipseMemoryHealth> {
  return request<EclipseMemoryHealth>("/eclipse-memory/health", { method: "GET" });
}

export async function memoryOverview(): Promise<MemoryOverview> {
  const body = await request<MemoryOverview & { success: boolean }>("/eclipse-memory/overview", { method: "GET" });
  return body;
}

export async function listMemories(filters: {
  memoryType?: string;
  scope?: string;
  status?: string;
  limit?: number;
} = {}): Promise<MemoryRecord[]> {
  const params = new URLSearchParams();
  if (filters.memoryType) params.set("memoryType", filters.memoryType);
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit ?? 100));
  const body = await request<{ memories: MemoryRecord[] }>(`/eclipse-memory/memories?${params}`, { method: "GET" });
  return body.memories ?? [];
}

export async function getMemory(memoryId: string): Promise<MemoryDetail | null> {
  try {
    const body = await request<{ memory: MemoryRecord; evidence: MemoryDetail["evidence"]; links: MemoryDetail["links"]; explanation?: MemoryDetail["explanation"] }>(
      `/eclipse-memory/memories/${encodeURIComponent(memoryId)}`,
      { method: "GET" }
    );
    return { memory: body.memory, evidence: body.evidence ?? [], links: body.links ?? [], explanation: body.explanation ?? null };
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
}

export async function memoryLifecycle(view?: string, scopeId?: string, limit = 100): Promise<MemoryLifecycleResponse> {
  const params = new URLSearchParams();
  if (view) params.set("view", view);
  if (scopeId) params.set("scopeId", scopeId);
  params.set("limit", String(limit));
  return request<MemoryLifecycleResponse>(`/eclipse-memory/lifecycle?${params.toString()}`, { method: "GET" });
}

export async function memoryRetention(): Promise<MemoryRetentionStatus> {
  return request<MemoryRetentionStatus>("/eclipse-memory/retention", { method: "GET" });
}

export async function memorySemanticStatus(): Promise<MemorySemanticStatus> {
  return request<MemorySemanticStatus>("/eclipse-memory/semantic-status", { method: "GET" });
}

export async function rebuildSemanticIndex(): Promise<{
  success: boolean;
  rebuilt: boolean;
  persistentIndex: boolean;
  reason: string;
  backend: string;
  available: boolean;
}> {
  return request("/eclipse-memory/semantic/rebuild", { method: "POST", body: JSON.stringify({}) });
}

export async function restoreMemory(memoryId: string, operator: boolean) {
  return request<{ success: boolean; memory: MemoryRecord }>(
    `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/restore`,
    { method: "POST", body: JSON.stringify({ operator }) }
  );
}

export async function renewMemory(memoryId: string, operator: boolean, days?: number) {
  return request<{ success: boolean; memory: MemoryRecord }>(
    `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/renew`,
    { method: "POST", body: JSON.stringify({ operator, days }) }
  );
}

export async function retentionSweep(operator: boolean) {
  return request<{ success: boolean; expired: number; ids: string[] }>(
    "/eclipse-memory/retention/sweep",
    { method: "POST", body: JSON.stringify({ operator }) }
  );
}

export async function exportMemory(): Promise<MemoryExportDocument> {
  return request<MemoryExportDocument>("/eclipse-memory/export", { method: "GET" });
}

export async function importMemory(
  document: MemoryExportDocument,
  operator: boolean,
  dryRun = false
): Promise<{ success: boolean; imported: number; skipped: number; rejected: Array<{ index: number; reason: string }>; dryRun: boolean }> {
  return request("/eclipse-memory/import", {
    method: "POST",
    body: JSON.stringify({ operator, document, dryRun }),
  });
}

export async function backupMemory(operator: boolean) {
  return request<{ success: boolean; path: string; bytes: number }>("/eclipse-memory/backup", {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function memoryDatabaseHealth(): Promise<MemoryDatabaseHealth> {
  return request<MemoryDatabaseHealth>("/eclipse-memory/database-health", { method: "GET" });
}

export async function resetMemory(operator: boolean, confirm: boolean): Promise<{ success: boolean; cleared: Record<string, number>; backup: { path: string } | null }> {
  return request("/eclipse-memory/reset", {
    method: "POST",
    body: JSON.stringify({ operator, confirm, backupFirst: true }),
  });
}

export async function createMemory(payload: {
  memoryType: string;
  content: string;
  source?: string;
  scope?: string;
  scopeId?: string;
  subject?: string;
  confidence?: number;
  verification?: string;
}, operator: boolean): Promise<MemoryRecord> {
  const body = await request<{ memory: MemoryRecord }>("/eclipse-memory/memories", {
    method: "POST",
    body: JSON.stringify({ ...payload, operator }),
  });
  return body.memory;
}

export async function archiveMemory(memoryId: string, operator: boolean, status = "archived") {
  return request<{ success: boolean; memory: MemoryRecord }>(
    `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/archive`,
    { method: "POST", body: JSON.stringify({ operator, status }) }
  );
}

export async function reviewMemory(memoryId: string, operator: boolean, approve: boolean) {
  return request<{ success: boolean; memory: MemoryRecord }>(
    `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/review`,
    { method: "POST", body: JSON.stringify({ operator, approve }) }
  );
}

export async function retrieveMemories(payload: {
  query: string;
  types?: string[];
  actorScope?: string;
  scopeId?: string;
  subject?: string;
  budgetChars?: number;
  limit?: number;
}): Promise<{ memories: MemoryRecord[]; context: string; diagnostics: MemoryRetrievalDiagnostics }> {
  return request("/eclipse-memory/retrieve", { method: "POST", body: JSON.stringify(payload) });
}

export async function listCorrections(): Promise<CorrectionRecord[]> {
  const body = await request<{ corrections: CorrectionRecord[] }>("/eclipse-memory/corrections", { method: "GET" });
  return body.corrections ?? [];
}

export async function createCorrection(payload: {
  wrong: string;
  correction: string;
  subject?: string;
  runId?: string;
  providedBy?: string;
  scope?: string;
  generalizable?: boolean;
}, operator: boolean) {
  return request<{ success: boolean; correctionId: string; generalizable: boolean }>(
    "/eclipse-memory/corrections",
    { method: "POST", body: JSON.stringify({ ...payload, operator }) }
  );
}

export async function listMistakes(): Promise<MistakeRecord[]> {
  const body = await request<{ mistakes: MistakeRecord[] }>("/eclipse-memory/mistakes", { method: "GET" });
  return body.mistakes ?? [];
}

export async function listMemoryEvents() {
  return request<{ events: Array<Record<string, unknown>>; skillEvents: Array<Record<string, unknown>> }>(
    "/eclipse-memory/events",
    { method: "GET" }
  );
}

export async function getPolicies(): Promise<{
  policies: Record<string, unknown>;
  defaults: Record<string, unknown>;
  bounds: Record<string, [number, number]>;
  locked: Record<string, unknown>;
  budget?: { limit: number; active: number; unlimited: boolean; full: boolean; remaining: number | null };
}> {
  return request("/eclipse-memory/policies", { method: "GET" });
}

export async function updatePolicies(
  policies: Record<string, unknown>,
  operator: boolean
): Promise<{ success: boolean; applied: unknown[]; policies: Record<string, unknown> }> {
  return request("/eclipse-memory/policies", {
    method: "PUT",
    body: JSON.stringify({ policies, operator }),
  });
}

export async function analyzeRun(runId: string): Promise<Record<string, unknown>> {
  return request(`/eclipse-memory/analyze/${encodeURIComponent(runId)}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export interface MemorySuggestion {
  id: string;
  runId: string | null;
  scope: string;
  scopeId: string | null;
  subject: string | null;
  memoryType: string;
  content: string;
  reason: string | null;
  provenance: string | null;
  confidence: number;
  status: string;
  createdAt: string;
  decidedAt: string | null;
}

export async function listSuggestions(status = "pending", scopeId?: string): Promise<MemorySuggestion[]> {
  const params = new URLSearchParams({ status });
  if (scopeId) params.set("scopeId", scopeId);
  const body = await request<{ suggestions: MemorySuggestion[] }>(
    `/eclipse-memory/suggestions?${params.toString()}`,
    { method: "GET" }
  );
  return body.suggestions ?? [];
}

export async function acceptSuggestion(id: string, operator: boolean, userId?: string) {
  return request<{ success: boolean; action: string }>(
    `/eclipse-memory/suggestions/${encodeURIComponent(id)}/accept`,
    { method: "POST", body: JSON.stringify({ operator, userId }) }
  );
}

export async function dismissSuggestion(id: string, operator: boolean, userId?: string) {
  return request<{ success: boolean; action: string }>(
    `/eclipse-memory/suggestions/${encodeURIComponent(id)}/dismiss`,
    { method: "POST", body: JSON.stringify({ operator, userId }) }
  );
}
