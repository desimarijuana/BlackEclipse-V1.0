// ─── Eclipse-Memory browser client (Phase 3-M) ──────────────────────────────
// The UI talks to the Next.js API routes, which proxy to the Python runtime.
// Client-safe: fetch only. Operator actions are re-checked server-side.

import type {
  CorrectionRecord,
  EclipseMemoryHealth,
  MemoryDetail,
  MemoryOverview,
  MemoryRecord,
  MemoryRetrievalDiagnostics,
  MistakeRecord,
} from "./eclipse-memory-types";

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

/** Presentation hint only — the server enforces authorization independently. */
export function clientIsOperator(): boolean {
  return typeof window !== "undefined";
}

export async function memoryHealth(): Promise<EclipseMemoryHealth> {
  return api<EclipseMemoryHealth>("/api/eclipse-memory/health");
}

export async function memoryOverview(): Promise<MemoryOverview> {
  return api<MemoryOverview>("/api/eclipse-memory/overview");
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
  const body = await api<{ memories: MemoryRecord[] }>(`/api/eclipse-memory/memories?${params}`);
  return body.memories ?? [];
}

export async function getMemory(memoryId: string): Promise<MemoryDetail | null> {
  const res = await fetch(`/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}`);
  if (res.status === 404) return null;
  const body = (await res.json().catch(() => ({}))) as MemoryDetail & { error?: string };
  if (!res.ok) throw new Error(body.error ?? "memory lookup failed");
  return body.memory ? body : null;
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
}): Promise<MemoryRecord> {
  const body = await api<{ memory: MemoryRecord }>("/api/eclipse-memory/memories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.memory;
}

export async function archiveMemory(memoryId: string, status = "archived") {
  return api<{ success: boolean; memory: MemoryRecord }>(
    `/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/archive`,
    { method: "POST", body: JSON.stringify({ status }) }
  );
}

export async function reviewMemory(memoryId: string, approve: boolean) {
  return api<{ success: boolean; memory: MemoryRecord }>(
    `/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/review`,
    { method: "POST", body: JSON.stringify({ approve }) }
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
  return api("/api/eclipse-memory/retrieve", { method: "POST", body: JSON.stringify(payload) });
}

export async function listCorrections(): Promise<CorrectionRecord[]> {
  const body = await api<{ corrections: CorrectionRecord[] }>("/api/eclipse-memory/corrections");
  return body.corrections ?? [];
}

export async function createCorrection(payload: {
  wrong: string;
  correction: string;
  subject?: string;
  runId?: string;
  scope?: string;
  generalizable?: boolean;
}) {
  return api<{ success: boolean; correctionId: string }>("/api/eclipse-memory/corrections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMistakes(): Promise<MistakeRecord[]> {
  const body = await api<{ mistakes: MistakeRecord[] }>("/api/eclipse-memory/mistakes");
  return body.mistakes ?? [];
}

export interface MemoryPolicies {
  policies: Record<string, unknown>;
  defaults: Record<string, unknown>;
  bounds: Record<string, [number, number]>;
  locked: Record<string, unknown>;
}

export async function getPolicies(): Promise<MemoryPolicies> {
  return api<MemoryPolicies>("/api/eclipse-memory/policies");
}

export async function updatePolicies(policies: Record<string, unknown>) {
  return api<{ success: boolean; applied: unknown[]; policies: Record<string, unknown> }>(
    "/api/eclipse-memory/policies",
    { method: "PUT", body: JSON.stringify({ policies }) }
  );
}

export async function analyzeRun(runId: string) {
  return api<Record<string, unknown>>(`/api/eclipse-memory/analyze/${encodeURIComponent(runId)}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
