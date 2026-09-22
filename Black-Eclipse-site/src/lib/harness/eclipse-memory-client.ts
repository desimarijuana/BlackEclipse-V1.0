// ─── Eclipse-Memory server client (front door) ──────────────────────────────
// Thin typed wrapper over the Python runtime's /eclipse-memory endpoints. It
// adds no memory logic. The browser MUST NOT import this file (it pulls the
// Python client); use `eclipse-memory-browser.ts`.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";
import type {
  CorrectionRecord,
  EclipseMemoryHealth,
  MemoryDetail,
  MemoryOverview,
  MemoryRecord,
  MemoryRetrievalDiagnostics,
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
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(rest.headers ?? {}) },
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
    const body = await request<{ memory: MemoryRecord; evidence: MemoryDetail["evidence"]; links: MemoryDetail["links"] }>(
      `/eclipse-memory/memories/${encodeURIComponent(memoryId)}`,
      { method: "GET" }
    );
    return { memory: body.memory, evidence: body.evidence ?? [], links: body.links ?? [] };
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
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
