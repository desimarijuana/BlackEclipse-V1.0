// ─── Eclipse-Memory browser client (Phase 3-M) ──────────────────────────────
// The UI talks to the Next.js API routes, which proxy to the Python runtime.
// Client-safe: fetch only. Operator actions are re-checked server-side.

import type {
  ChatSessionRecord,
  CorrectionRecord,
  EclipseMemoryHealth,
  LearningReviewHealth,
  LearningReviewRecord,
  MemoryDatabaseHealth,
  CompactionProposal,
  MemoryConflictReview,
  MemoryDetail,
  MemoryExportDocument,
  MemoryProfileRecord,
  MemoryLifecycleResponse,
  MemoryOverview,
  MemoryProfileResponse,
  MemoryRecord,
  MemoryRetentionStatus,
  MemoryRetrievalDiagnostics,
  MemoryProviderSearchResponse,
  MemoryProviderStatus,
  MemoryProviderTestResult,
  MemoryUsageReport,
  MistakeRecord,
  PreferenceSummary,
  SessionSearchHit,
  SessionOpenResult,
  SessionSearchHealth,
  SessionSearchResult,
} from "../eclipse-memory-types";

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

/** Active learned preferences, pending inferences and the evidence behind them. */
export async function memoryPreferences(scopeId?: string): Promise<PreferenceSummary> {
  const qs = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : "";
  return api<PreferenceSummary>(`/api/eclipse-memory/preferences${qs}`);
}

/** Run the deterministic learner now. Creates inert suggestions only. */
export async function learnPreferences(userId?: string, runId?: string): Promise<{
  success: boolean;
  mode: string;
  created: Array<Record<string, unknown>>;
  saved: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  observationCount: number;
}> {
  return api("/api/eclipse-memory/preferences/learn", {
    method: "POST",
    body: JSON.stringify({ userId, runId }),
  });
}

export interface MemoryListPage {
  memories: MemoryRecord[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export async function listMemoriesPage(filters: {
  memoryType?: string;
  scope?: string;
  status?: string;
  scopeId?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<MemoryListPage> {
  const params = new URLSearchParams();
  if (filters.memoryType) params.set("memoryType", filters.memoryType);
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.status) params.set("status", filters.status);
  if (filters.scopeId) params.set("scopeId", filters.scopeId);
  if (filters.search) params.set("q", filters.search);
  params.set("limit", String(filters.limit ?? 100));
  params.set("offset", String(filters.offset ?? 0));
  const body = await api<MemoryListPage & { memories: MemoryRecord[] }>(`/api/eclipse-memory/memories?${params}`);
  return {
    memories: body.memories ?? [],
    total: Number(body.total ?? (body.memories?.length ?? 0)),
    limit: Number(body.limit ?? filters.limit ?? 50),
    offset: Number(body.offset ?? filters.offset ?? 0),
    hasMore: Boolean(body.hasMore),
  };
}

export async function listMemories(filters: {
  memoryType?: string;
  scope?: string;
  status?: string;
  scopeId?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<MemoryRecord[]> {
  return (await listMemoriesPage(filters)).memories;
}

/**
 * The durable memories one conversation owns (its private per-conversation
 * bucket). Bots use this for their Memory panel.
 */
export async function listConversationMemories(conversationId: string, limit = 100): Promise<MemoryRecord[]> {
  return listMemories({ scope: "conversation", scopeId: conversationId, limit });
}

/** Forget (archive) one conversation's private memory. Operator-gated. */
export async function forgetConversation(conversationId: string) {
  return api<{ success: boolean; archived: string[] }>(
    `/api/eclipse-memory/conversations/${encodeURIComponent(conversationId)}/forget`,
    { method: "POST", body: JSON.stringify({ operator: true }) }
  );
}

export async function getMemory(memoryId: string): Promise<MemoryDetail | null> {
  const res = await fetch(`/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}`);
  if (res.status === 404) return null;
  const body = (await res.json().catch(() => ({}))) as MemoryDetail & { error?: string };
  if (!res.ok) throw new Error(body.error ?? "memory lookup failed");
  return body.memory ? body : null;
}

export async function listCompaction(status?: string): Promise<CompactionProposal[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await api<{ proposals: CompactionProposal[] }>(`/api/eclipse-memory/compaction${query}`);
  return body.proposals ?? [];
}

export async function detectCompaction(): Promise<CompactionProposal[]> {
  const body = await api<{ proposals: CompactionProposal[] }>(`/api/eclipse-memory/compaction/detect`, { method: "POST" });
  return body.proposals ?? [];
}

export async function acceptCompaction(proposalId: string, mergedContent?: string): Promise<{ ok: boolean; error?: string; mergedInto?: string }> {
  return api(`/api/eclipse-memory/compaction/${encodeURIComponent(proposalId)}/accept`, {
    method: "POST", body: JSON.stringify({ mergedContent }),
  });
}

export async function rejectCompaction(proposalId: string): Promise<{ ok: boolean }> {
  return api(`/api/eclipse-memory/compaction/${encodeURIComponent(proposalId)}/reject`, { method: "POST" });
}

export async function memoryConflictReview(memoryId: string): Promise<MemoryConflictReview | null> {
  const res = await fetch(`/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/conflict`);
  if (res.status === 404) return null;
  const body = (await res.json().catch(() => ({}))) as { review?: MemoryConflictReview; error?: string };
  if (!res.ok) throw new Error(body.error ?? "conflict review failed");
  return body.review ?? null;
}

export async function resolveMemoryConflict(
  memoryId: string,
  action: string,
  opts: { targetId?: string; mergedContent?: string; reason?: string } = {},
): Promise<{ ok: boolean; error?: string }> {
  return api(`/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ action, ...opts }),
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

export async function memoryLifecycle(view?: string, scopeId?: string, limit = 50, offset = 0): Promise<MemoryLifecycleResponse> {
  const params = new URLSearchParams();
  if (view) params.set("view", view);
  if (scopeId) params.set("scopeId", scopeId);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return api<MemoryLifecycleResponse>(`/api/eclipse-memory/lifecycle?${params.toString()}`);
}

export async function memoryRetention(): Promise<MemoryRetentionStatus> {
  return api<MemoryRetentionStatus>("/api/eclipse-memory/retention");
}

export async function memoryUsageReport(windowDays = 30): Promise<MemoryUsageReport> {
  return api<MemoryUsageReport>(`/api/eclipse-memory/usage-report?windowDays=${windowDays}`);
}

export async function labelConflict(
  memoryId: string, label: "true_conflict" | "false_positive", reason?: string,
): Promise<{ success: boolean }> {
  return api(`/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/conflict-label`, {
    method: "POST",
    body: JSON.stringify({ operator: true, label, reason }),
  });
}

// ── Memory providers (M8) ───────────────────────────────────────────────────

export async function memoryProviderStatus(): Promise<MemoryProviderStatus> {
  return api<MemoryProviderStatus>("/api/memory-providers/status");
}

export async function memoryProviderSearch(params: {
  query: string;
  scopeId?: string;
  limit?: number;
  allowExternal?: boolean;
}): Promise<MemoryProviderSearchResponse> {
  return api<MemoryProviderSearchResponse>("/api/memory-providers/search", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function memoryProviderTest(provider: string): Promise<MemoryProviderTestResult> {
  return api<MemoryProviderTestResult>("/api/memory-providers/test", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export async function memoryProfile(scopeId?: string): Promise<MemoryProfileResponse> {
  const params = new URLSearchParams();
  if (scopeId) params.set("scopeId", scopeId);
  const qs = params.toString();
  return api<MemoryProfileResponse>(`/api/eclipse-memory/profile${qs ? `?${qs}` : ""}`);
}

export async function rebuildProfile(scopeId?: string): Promise<MemoryProfileResponse & { rebuilt: boolean }> {
  return api(`/api/eclipse-memory/profile/rebuild`, {
    method: "POST",
    body: JSON.stringify({ scopeId }),
  });
}

// ── Session history search (M2) ─────────────────────────────────────────────

export async function sessionSearchHealth(): Promise<SessionSearchHealth> {
  return api<SessionSearchHealth>("/api/session-search/health");
}

export async function sessionSearch(params: {
  q: string;
  scopeId?: string;
  scope?: string;
  runId?: string;
  sessionId?: string;
  profileId?: string;
  role?: string;
  kind?: string;
  market?: string;
  skillId?: string;
  memoryAction?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
}): Promise<SessionSearchResult> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.scopeId) qs.set("scopeId", params.scopeId);
  if (params.scope) qs.set("scope", params.scope);
  if (params.runId) qs.set("runId", params.runId);
  if (params.sessionId) qs.set("sessionId", params.sessionId);
  if (params.profileId) qs.set("profileId", params.profileId);
  if (params.role) qs.set("role", params.role);
  if (params.kind) qs.set("kind", params.kind);
  if (params.market) qs.set("market", params.market);
  if (params.skillId) qs.set("skillId", params.skillId);
  if (params.memoryAction) qs.set("memoryAction", params.memoryAction);
  if (params.dateFrom) qs.set("dateFrom", params.dateFrom);
  if (params.dateTo) qs.set("dateTo", params.dateTo);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  return api<SessionSearchResult>(`/api/session-search?${qs.toString()}`);
}

// ── Named sessions + profiles (M3/M4) ───────────────────────────────────────

export interface SessionPage {
  sessions: ChatSessionRecord[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export async function listChatSessionsPage(
  params: { profileId?: string; userId?: string; status?: string; limit?: number; offset?: number } = {},
): Promise<SessionPage> {
  const qs = new URLSearchParams();
  if (params.profileId) qs.set("profileId", params.profileId);
  if (params.userId) qs.set("userId", params.userId);
  if (params.status) qs.set("status", params.status);
  qs.set("limit", String(params.limit ?? 50));
  qs.set("offset", String(params.offset ?? 0));
  const body = await api<SessionPage & { sessions: ChatSessionRecord[] }>(`/api/sessions?${qs.toString()}`);
  return {
    sessions: body.sessions ?? [],
    total: Number(body.total ?? (body.sessions?.length ?? 0)),
    limit: Number(body.limit ?? params.limit ?? 50),
    offset: Number(body.offset ?? params.offset ?? 0),
    hasMore: Boolean(body.hasMore),
  };
}

export async function listChatSessions(params: { profileId?: string; userId?: string; status?: string; limit?: number; offset?: number } = {}): Promise<ChatSessionRecord[]> {
  return (await listChatSessionsPage(params)).sessions;
}

export async function getChatSession(sessionId: string): Promise<{ session: ChatSessionRecord; runs: string[] }> {
  return api(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export async function createChatSession(payload: { profileId?: string; userId?: string; title?: string }): Promise<{ session: ChatSessionRecord }> {
  return api("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateChatSession(sessionId: string, patch: Record<string, unknown>): Promise<{ session: ChatSessionRecord }> {
  return api(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export async function forkChatSession(sessionId: string): Promise<{ session: ChatSessionRecord }> {
  return api(`/api/sessions/${encodeURIComponent(sessionId)}/fork`, { method: "POST", body: JSON.stringify({}) });
}

export async function deleteChatSession(sessionId: string, hard = false) {
  return api<{ success: boolean }>(`/api/sessions/${encodeURIComponent(sessionId)}?hard=${hard}`, { method: "DELETE" });
}

export async function exportChatSession(sessionId: string): Promise<{ session: ChatSessionRecord; messages: SessionSearchHit[] }> {
  return api(`/api/sessions/${encodeURIComponent(sessionId)}/export`);
}

export async function getSessionSummary(sessionId: string): Promise<{ success: boolean; summary: Record<string, unknown> }> {
  return api(`/api/sessions/${encodeURIComponent(sessionId)}/summary`);
}

export async function listProfiles(): Promise<MemoryProfileRecord[]> {
  const body = await api<{ profiles: MemoryProfileRecord[] }>("/api/profiles");
  return body.profiles ?? [];
}

export async function createProfile(payload: { id: string; name?: string; inherits?: string; retentionDays?: number }): Promise<{ profile: MemoryProfileRecord }> {
  return api("/api/profiles", { method: "POST", body: JSON.stringify(payload) });
}

export async function getProfile(profileId: string): Promise<{ profile: MemoryProfileRecord; inherited: string[] }> {
  return api(`/api/profiles/${encodeURIComponent(profileId)}`);
}

export async function updateProfile(profileId: string, patch: Record<string, unknown>): Promise<{ profile: MemoryProfileRecord }> {
  return api(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export async function deleteProfile(profileId: string) {
  return api<{ success: boolean }>(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
}

export async function sessionOpen(runId: string): Promise<SessionOpenResult> {
  return api<SessionOpenResult>(`/api/session-search/${encodeURIComponent(runId)}`);
}

export async function sessionDelete(runId: string) {
  return api<{ success: boolean; removed: number }>(
    `/api/session-search/delete/${encodeURIComponent(runId)}`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

// ── Learning review (M3) ────────────────────────────────────────────────────

export async function learningReviewHealth(): Promise<LearningReviewHealth> {
  return api<LearningReviewHealth>("/api/learning-review/health");
}

export interface LearningReviewPage {
  reviews: LearningReviewRecord[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export async function listLearningReviewsPage(
  status?: string, limit = 50, offset = 0,
): Promise<LearningReviewPage> {
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  qs.set("limit", String(limit));
  qs.set("offset", String(offset));
  const body = await api<LearningReviewPage & { reviews: LearningReviewRecord[] }>(`/api/learning-review?${qs.toString()}`);
  return {
    reviews: body.reviews ?? [],
    total: Number(body.total ?? (body.reviews?.length ?? 0)),
    limit: Number(body.limit ?? limit),
    offset: Number(body.offset ?? offset),
    hasMore: Boolean(body.hasMore),
  };
}

export async function listLearningReviews(status?: string, limit = 50): Promise<LearningReviewRecord[]> {
  return (await listLearningReviewsPage(status, limit, 0)).reviews;
}

export async function runLearningReview(runId: string, model = false) {
  return api<{ success: boolean; review: LearningReviewRecord }>("/api/learning-review/run", {
    method: "POST",
    body: JSON.stringify({ runId, model }),
  });
}

export async function decideLearningReview(reviewId: string, outcomeIndex: number, action: "accept" | "reject") {
  return api<{ success: boolean; action: string }>("/api/learning-review/decide", {
    method: "POST",
    body: JSON.stringify({ reviewId, outcomeIndex, action }),
  });
}

// ── Markdown file projection (M4) ───────────────────────────────────────────

export interface MemoryFiles {
  root: string;
  files: Record<string, string>;
}

export interface MarkdownImportPreview {
  success: boolean;
  preview: boolean;
  entries: Array<{ id: string | null; memoryType: string; scope: string; content: string }>;
  ignored: Array<{ file: string; reason: string }>;
}

export async function getMemoryFiles(): Promise<MemoryFiles> {
  return api<MemoryFiles>("/api/eclipse-memory/files");
}

export async function regenerateMemoryFiles() {
  return api<{ success: boolean; root: string; backupDir: string | null; files: string[] }>(
    "/api/eclipse-memory/files/regenerate",
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function previewMarkdownImport(): Promise<MarkdownImportPreview> {
  return api<MarkdownImportPreview>("/api/eclipse-memory/import/markdown");
}

export async function importMarkdown(dryRun = false) {
  return api<{ success: boolean; imported: number; skipped: number; rejected: Array<{ index: number; reason: string }>; backupDir: string | null; ignored: Array<{ file: string; reason: string }> }>(
    "/api/eclipse-memory/import/markdown",
    { method: "POST", body: JSON.stringify({ dryRun }) }
  );
}

export async function restoreMemoryFiles(backupId?: string) {
  return api<{ success: boolean; restored: boolean; from: string | null }>(
    "/api/eclipse-memory/files/restore",
    { method: "POST", body: JSON.stringify({ backupId }) }
  );
}

// ── File edit + history (M6) ────────────────────────────────────────────────

export type FileEditOperation = "add" | "replace" | "merge" | "split" | "reorder" | "consolidate";

export async function editMemoryFile(payload: {
  operation: FileEditOperation;
  file: string;
  memoryId?: string;
  expectedVersion?: string;
  content?: string;
}) {
  return api<{ ok: boolean; error?: string; entries?: Array<unknown> }>(
    "/api/eclipse-memory/files/edit",
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export interface FileRevision {
  revision: string;
  at: string;
  actor: string;
  reason: string;
  affectedIds: string[];
  parentRevision: string | null;
}

export async function listFileHistory(file: string, revision?: string): Promise<{
  success: boolean;
  revisions: FileRevision[];
  diff: Array<{ type: "add" | "remove" | "same"; line: string }> | null;
}> {
  const qs = new URLSearchParams({ file });
  if (revision) qs.set("revision", revision);
  return api(`/api/eclipse-memory/files/history?${qs.toString()}`);
}

export async function rollbackMemoryFile(file: string, revision: string) {
  return api<{ success: boolean; restored: boolean; from: string | null }>(
    "/api/eclipse-memory/files/history",
    { method: "POST", body: JSON.stringify({ file, revision }) }
  );
}

export async function restoreMemory(memoryId: string) {
  return api<{ success: boolean; memory: MemoryRecord }>(
    `/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/restore`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function renewMemory(memoryId: string, days?: number) {
  return api<{ success: boolean; memory: MemoryRecord }>(
    `/api/eclipse-memory/memories/${encodeURIComponent(memoryId)}/renew`,
    { method: "POST", body: JSON.stringify({ days }) }
  );
}

export async function exportMemory(): Promise<MemoryExportDocument> {
  return api<MemoryExportDocument>("/api/eclipse-memory/export");
}

export async function importMemory(
  document: MemoryExportDocument,
  dryRun = false
): Promise<{
  success: boolean; imported: number; skipped: number;
  rejected: Array<{ index: number; reason: string }>; dryRun: boolean;
  importable?: number; checksumOk?: boolean | null;
  importedEvaluations?: number; auditRestored?: number;
  preview?: {
    new: number; duplicate: number; invalid: number; superseding: number;
    items: Array<{ index: number; kind: string; existingId?: string }>;
  };
}> {
  return api("/api/eclipse-memory/import", {
    method: "POST",
    body: JSON.stringify({ document, dryRun }),
  });
}

export async function backupMemory() {
  return api<{ success: boolean; path: string; bytes: number }>("/api/eclipse-memory/backup", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function memoryDatabaseHealth(): Promise<MemoryDatabaseHealth> {
  return api<MemoryDatabaseHealth>("/api/eclipse-memory/database-health");
}

export async function resetMemory(confirm: boolean) {
  return api<{ success: boolean; cleared: Record<string, number>; backup: { path: string } | null }>(
    "/api/eclipse-memory/reset",
    { method: "POST", body: JSON.stringify({ confirm }) }
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

export interface RecordPage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export async function listCorrections(limit = 50, offset = 0): Promise<CorrectionRecord[]> {
  return (await listCorrectionsPage(limit, offset)).items;
}

export async function listCorrectionsPage(limit = 50, offset = 0): Promise<RecordPage<CorrectionRecord>> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const body = await api<{
    corrections: CorrectionRecord[]; total?: number; limit?: number; offset?: number; hasMore?: boolean;
  }>(`/api/eclipse-memory/corrections?${qs.toString()}`);
  return {
    items: body.corrections ?? [],
    total: Number(body.total ?? (body.corrections?.length ?? 0)),
    limit: Number(body.limit ?? limit),
    offset: Number(body.offset ?? offset),
    hasMore: Boolean(body.hasMore),
  };
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

export async function listMistakes(limit = 50, offset = 0): Promise<MistakeRecord[]> {
  return (await listMistakesPage(limit, offset)).items;
}

export async function listMistakesPage(limit = 50, offset = 0): Promise<RecordPage<MistakeRecord>> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const body = await api<{
    mistakes: MistakeRecord[]; total?: number; limit?: number; offset?: number; hasMore?: boolean;
  }>(`/api/eclipse-memory/mistakes?${qs.toString()}`);
  return {
    items: body.mistakes ?? [],
    total: Number(body.total ?? (body.mistakes?.length ?? 0)),
    limit: Number(body.limit ?? limit),
    offset: Number(body.offset ?? offset),
    hasMore: Boolean(body.hasMore),
  };
}

export interface MemoryPolicies {
  policies: Record<string, unknown>;
  defaults: Record<string, unknown>;
  bounds: Record<string, [number, number]>;
  locked: Record<string, unknown>;
  budget?: MemoryBudget;
}

export interface MemoryBudget {
  limit: number;
  active: number;
  unlimited: boolean;
  full: boolean;
  remaining: number | null;
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

export async function listSuggestions(status = "pending"): Promise<MemorySuggestion[]> {
  return (await listSuggestionsPage(status, 50, 0)).items;
}

export async function listSuggestionsPage(
  status = "pending", limit = 50, offset = 0,
): Promise<RecordPage<MemorySuggestion>> {
  const qs = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  const body = await api<{
    suggestions: MemorySuggestion[]; total?: number; limit?: number; offset?: number; hasMore?: boolean;
  }>(`/api/eclipse-memory/suggestions?${qs.toString()}`);
  return {
    items: body.suggestions ?? [],
    total: Number(body.total ?? (body.suggestions?.length ?? 0)),
    limit: Number(body.limit ?? limit),
    offset: Number(body.offset ?? offset),
    hasMore: Boolean(body.hasMore),
  };
}

export async function acceptSuggestion(id: string, userId?: string) {
  return api<{ success: boolean; action: string }>("/api/eclipse-memory/suggestions", {
    method: "POST",
    body: JSON.stringify({ id, action: "accept", userId }),
  });
}

export async function dismissSuggestion(id: string) {
  return api<{ success: boolean; action: string }>("/api/eclipse-memory/suggestions", {
    method: "POST",
    body: JSON.stringify({ id, action: "dismiss" }),
  });
}
