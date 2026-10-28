// ─── Eclipse-Memory server client (front door) ──────────────────────────────
// Thin typed wrapper over the Python runtime's /eclipse-memory endpoints. It
// adds no memory logic. The browser MUST NOT import this file (it pulls the
// Python client); use `eclipse-memory-browser.ts`.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets, HarnessHttpError, isNotFoundError } from "./errors";
import type {
  CorrectionRecord,
  EclipseMemoryHealth,
  LearningReviewHealth,
  LearningReviewRecord,
  MemoryDatabaseHealth,
  CompactionProposal,
  MemoryConflictReview,
  MemoryDetail,
  MemoryExportDocument,
  MemoryLifecycleResponse,
  MemoryOverview,
  MemoryRecord,
  MemoryProfileResponse,
  MemoryRetentionStatus,
  MemoryRetrievalDiagnostics,
  MemoryProviderSearchResponse,
  MemoryProviderStatus,
  MemoryProviderTestResult,
  MemoryUsageReport,
  MistakeRecord,
  PreferenceSummary,
  SessionOpenResult,
  SessionSearchHealth,
  SessionSearchResult,
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
    throw new HarnessHttpError(res.status, redactSecrets(detail), detail);
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

export async function memoryPreferences(scopeId?: string): Promise<PreferenceSummary> {
  const qs = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : "";
  return request<PreferenceSummary>(`/eclipse-memory/preferences${qs}`, { method: "GET" });
}

export async function learnPreferences(userId?: string, runId?: string): Promise<{
  success: boolean;
  mode: string;
  created: Array<Record<string, unknown>>;
  saved: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  observationCount: number;
}> {
  return request("/eclipse-memory/preferences/learn", {
    method: "POST",
    body: JSON.stringify({ userId, runId }),
  });
}

export async function listMemories(filters: {
  memoryType?: string;
  scope?: string;
  status?: string;
  scopeId?: string;
  limit?: number;
} = {}): Promise<MemoryRecord[]> {
  const params = new URLSearchParams();
  if (filters.memoryType) params.set("memoryType", filters.memoryType);
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.status) params.set("status", filters.status);
  if (filters.scopeId) params.set("scopeId", filters.scopeId);
  params.set("limit", String(filters.limit ?? 100));
  const body = await request<{ memories: MemoryRecord[] }>(`/eclipse-memory/memories?${params}`, { method: "GET" });
  return body.memories ?? [];
}

/** Forget (archive) one conversation's private memory. Operator-gated in Python. */
export async function forgetConversation(
  conversationId: string,
  operator = true,
): Promise<{ success: boolean; archived: string[] }> {
  return request(`/eclipse-memory/conversations/${encodeURIComponent(conversationId)}/forget`, {
    method: "POST", body: JSON.stringify({ operator }),
  });
}

export async function getMemory(memoryId: string): Promise<MemoryDetail | null> {
  try {
    const body = await request<{ memory: MemoryRecord; evidence: MemoryDetail["evidence"]; links: MemoryDetail["links"]; explanation?: MemoryDetail["explanation"] }>(
      `/eclipse-memory/memories/${encodeURIComponent(memoryId)}`,
      { method: "GET" }
    );
    return { memory: body.memory, evidence: body.evidence ?? [], links: body.links ?? [], explanation: body.explanation ?? null };
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function listCompaction(status?: string): Promise<CompactionProposal[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await request<{ proposals: CompactionProposal[] }>(`/eclipse-memory/compaction${query}`, { method: "GET" });
  return body.proposals ?? [];
}

export async function detectCompaction(): Promise<CompactionProposal[]> {
  const body = await request<{ proposals: CompactionProposal[] }>("/eclipse-memory/compaction/detect", {
    method: "POST", body: JSON.stringify({ operator: true }),
  });
  return body.proposals ?? [];
}

export async function acceptCompaction(proposalId: string, mergedContent?: string): Promise<{ ok: boolean; error?: string; mergedInto?: string }> {
  return request(`/eclipse-memory/compaction/${encodeURIComponent(proposalId)}/accept`, {
    method: "POST", body: JSON.stringify({ operator: true, mergedContent }),
  });
}

export async function rejectCompaction(proposalId: string): Promise<{ ok: boolean }> {
  return request(`/eclipse-memory/compaction/${encodeURIComponent(proposalId)}/reject`, {
    method: "POST", body: JSON.stringify({ operator: true }),
  });
}

export async function memoryConflictReview(memoryId: string): Promise<MemoryConflictReview | null> {
  try {
    const body = await request<{ review: MemoryConflictReview }>(
      `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/conflict`,
      { method: "GET" }
    );
    return body.review;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function resolveMemoryConflict(
  memoryId: string,
  action: string,
  opts: { targetId?: string; mergedContent?: string; reason?: string } = {},
): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>(
    `/eclipse-memory/memories/${encodeURIComponent(memoryId)}/resolve`,
    { method: "POST", body: JSON.stringify({ action, operator: true, ...opts }) }
  );
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

export async function memoryUsageReport(windowDays = 30): Promise<MemoryUsageReport> {
  return request<MemoryUsageReport>(`/eclipse-memory/usage-report?windowDays=${windowDays}`, { method: "GET" });
}

export async function labelConflict(
  memoryId: string, label: "true_conflict" | "false_positive", operator: boolean, reason?: string,
): Promise<{ success: boolean }> {
  return request(`/eclipse-memory/memories/${encodeURIComponent(memoryId)}/conflict-label`, {
    method: "POST",
    body: JSON.stringify({ operator, label, reason }),
  });
}

// ── Memory providers (M8) ───────────────────────────────────────────────────

export async function memoryProviderStatus(): Promise<MemoryProviderStatus> {
  return request<MemoryProviderStatus>("/memory-providers/status", { method: "GET" });
}

export async function memoryProviderSearch(params: {
  query: string;
  scope?: string;
  scopeId?: string;
  types?: string[];
  limit?: number;
  allowExternal?: boolean;
}): Promise<MemoryProviderSearchResponse> {
  return request<MemoryProviderSearchResponse>("/memory-providers/search", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function memoryProviderTest(provider: string): Promise<MemoryProviderTestResult> {
  return request<MemoryProviderTestResult>("/memory-providers/test", {
    method: "POST",
    body: JSON.stringify({ provider, operator: true }),
  });
}

export async function memoryProfile(scopeId?: string): Promise<MemoryProfileResponse> {
  const params = new URLSearchParams();
  if (scopeId) params.set("scopeId", scopeId);
  const qs = params.toString();
  return request<MemoryProfileResponse>(`/eclipse-memory/profile${qs ? `?${qs}` : ""}`, { method: "GET" });
}

export async function rebuildProfile(operator: boolean, scopeId?: string): Promise<MemoryProfileResponse & { rebuilt: boolean }> {
  return request(`/eclipse-memory/profile/rebuild`, {
    method: "POST",
    body: JSON.stringify({ operator, scopeId }),
  });
}

// ── Session history search (M2) ─────────────────────────────────────────────

export async function sessionSearchHealth(): Promise<SessionSearchHealth> {
  return request<SessionSearchHealth>("/session-search/health", { method: "GET" });
}

export async function sessionSearch(params: {
  q: string;
  scopeId?: string;
  scope?: string;
  runId?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
}): Promise<SessionSearchResult> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.scopeId) qs.set("scopeId", params.scopeId);
  if (params.scope) qs.set("scope", params.scope);
  if (params.runId) qs.set("runId", params.runId);
  if (params.dateFrom) qs.set("dateFrom", params.dateFrom);
  if (params.dateTo) qs.set("dateTo", params.dateTo);
  if (params.limit) qs.set("limit", String(params.limit));
  return request<SessionSearchResult>(`/session-search?${qs.toString()}`, { method: "GET" });
}

export async function sessionOpen(runId: string): Promise<SessionOpenResult> {
  return request<SessionOpenResult>(`/session-search/${encodeURIComponent(runId)}`, { method: "GET" });
}

export async function sessionReindex(operator: boolean, runId?: string, limit?: number) {
  return request<{ success: boolean; runs?: number; indexed: number }>("/session-search/reindex", {
    method: "POST",
    body: JSON.stringify({ operator, runId, limit }),
  });
}

export async function sessionDelete(runId: string, operator: boolean) {
  return request<{ success: boolean; removed: number }>(
    `/session-search/delete/${encodeURIComponent(runId)}`,
    { method: "POST", body: JSON.stringify({ operator }) }
  );
}

// ── Learning review (M3) ────────────────────────────────────────────────────

export async function learningReviewHealth(): Promise<LearningReviewHealth> {
  return request<LearningReviewHealth>("/learning-review/health", { method: "GET" });
}

export async function listLearningReviews(status?: string, limit = 50): Promise<LearningReviewRecord[]> {
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  qs.set("limit", String(limit));
  const body = await request<{ reviews: LearningReviewRecord[] }>(
    `/learning-review?${qs.toString()}`,
    { method: "GET" }
  );
  return body.reviews ?? [];
}

export async function runLearningReview(operator: boolean, runId: string, model = false) {
  return request<{ success: boolean; review: LearningReviewRecord }>(
    "/learning-review/run",
    { method: "POST", body: JSON.stringify({ operator, runId, model }) }
  );
}

export async function decideLearningReview(operator: boolean, reviewId: string, outcomeIndex: number, action: "accept" | "reject") {
  return request<{ success: boolean; action: string; memory?: Record<string, unknown> }>(
    "/learning-review/decide",
    { method: "POST", body: JSON.stringify({ operator, reviewId, outcomeIndex, action }) }
  );
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
  structuredData?: Record<string, unknown> | null;
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
