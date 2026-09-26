// ─── Eclipse-Memory TS contracts (Phase 3-M) ────────────────────────────────
// The memory database, write/retrieve pipelines and skill lifecycle live in
// Python (`python/harness/eclipse_memory/`). This file declares only the shapes
// the Next.js front door proxies and renders.

export type MemoryType =
  | "episodic" | "semantic" | "procedural" | "preference"
  | "constraint" | "correction" | "observation" | "summary";

export type MemoryStatus =
  | "proposed" | "active" | "archived" | "superseded" | "rejected" | "expired";

export type MemoryScope = "general" | "user" | "market" | "task";

export interface MemoryRecord {
  id: string;
  memoryType: MemoryType;
  scope: MemoryScope | string;
  scopeId: string | null;
  subject: string | null;
  content: string;
  structuredData?: Record<string, unknown> | null;
  source: string | null;
  sourceRunId: string | null;
  confidence: number;
  importance: number;
  status: MemoryStatus | string;
  verification: string;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  lastAccessedAt: string | null;
  accessCount: number;
  expiresAt: string | null;
  supersededBy: string | null;
  reviewedAt: string | null;
  reviewStatus: string | null;
  lastConfirmedAt?: string | null;
  lastUsedAt?: string | null;
  lastReviewedAt?: string | null;
  authority?: "explicit" | "automatic" | string;
  statusReason?: string | null;
}

export interface MemoryExplanation {
  memoryId: string;
  memoryType: string;
  scope: string;
  scopeId: string | null;
  authority: string;
  provenance: string;
  saveReason: string;
  status: string;
  statusReason: string | null;
  recallDisposition: string;
  timeline: {
    createdAt: string | null;
    lastConfirmedAt: string | null;
    lastUsedAt: string | null;
    lastReviewedAt: string | null;
    expiresAt: string | null;
  };
  supersededBy: string | null;
  verification: string | null;
  confidence: number | null;
  conflict?: MemoryConflictDetail | null;
}

export type MemoryLifecycleView =
  | "active" | "expired" | "superseded" | "rejected" | "archived"
  | "never-used" | "frequently-recalled" | "automatic" | "conflicts";

export interface MemoryLifecycleOverview {
  counts: Record<string, number>;
  views: Record<string, number>;
  budget: {
    limit: number;
    active: number;
    unlimited: boolean;
    full: boolean;
    remaining: number | null;
  };
}

export interface MemoryLifecycleResponse extends MemoryLifecycleOverview {
  view?: MemoryLifecycleView;
  memories?: MemoryRecord[];
}

export interface MemorySweepRecord {
  operation: string;
  ranAt: string;
  ok: boolean;
  inspected: number;
  expired: number;
  skipped: number;
  error: string | null;
}

export interface MemoryRetentionStatus {
  retentionDays: number;
  automaticExpiryEnabled: boolean;
  explicitMemoriesExempt: boolean;
  lastSweep: MemorySweepRecord | null;
}

export interface MemorySemanticBackendHealth {
  backend: string;
  version: string;
  available: boolean;
}

export interface MemorySemanticControls {
  enabled: boolean;
  backend: string;
  threshold: number | null;
  candidateLimit: number | null;
  indexLimit: number | null;
  timeoutMs: number | null;
  diagnostics: boolean;
}

export interface MemorySemanticStats {
  available: boolean;
  proposedBySemantics?: number;
  semanticCandidateOccurrences?: number;
  actionableCandidates?: number;
  diagnosticRuns?: number;
  confirmedAfterReview?: number;
  keptExistingOrDismissed?: number;
  replacementProposals?: number;
}

export interface MemorySemanticStatus {
  mode: "lexical" | "lexical+semantic" | "lexical+semantic-unavailable" | string;
  lexicalActive: boolean;
  semanticEnabled: boolean;
  semanticAvailable: boolean;
  backend: string;
  backendRequested?: string;
  detectorVersion: string;
  reason: string;
  controls?: MemorySemanticControls;
  backends?: MemorySemanticBackendHealth[];
  stats?: MemorySemanticStats;
}

export interface MemoryConflictDetail {
  decision: string;
  reason: string;
  detector: string;
  similarity: number | null;
  candidateIds: string[];
  authority: string;
  requiresConfirmation: boolean;
}

export interface MemoryEvidence {
  id: string;
  memoryId: string;
  sourceType: string;
  sourceRef: string | null;
  sourceUrl: string | null;
  sourceRunId: string | null;
  evidenceText: string | null;
  retrievedAt: string | null;
  publishedAt: string | null;
  verificationStatus: string;
  createdAt: string;
}

export interface MemoryDetail {
  memory: MemoryRecord;
  evidence: MemoryEvidence[];
  links: Array<{ id: string; fromId: string; toId: string; relation: string; note: string | null; createdAt: string }>;
  explanation?: MemoryExplanation | null;
}

export interface MemoryRetrievalDiagnostics {
  query: string;
  candidates: number;
  selected: number;
  excluded: Array<{ id: string; reason: string }>;
  selectionReasons: string[];
  budgetChars: number;
  usedChars: number;
  durationMs: number;
  ok: boolean;
  error: string | null;
}

export interface MemoryOverview {
  memories: { total: number; byType: Record<string, number>; byStatus: Record<string, number> };
  skills: { installed: number };
  candidates: number;
  corrections: number;
  mistakes: number;
  retrievals: number;
  suggestions: number;
  health: EclipseMemoryHealth;
}

export interface EclipseMemoryHealth {
  ok: boolean;
  integrity?: string;
  path: string;
  tables?: number;
  counts?: Record<string, number>;
  schemaVersion?: number;
  appliedVersions?: number[];
  upToDate?: boolean;
  memoryBudget?: { limit: number; active: number; unlimited: boolean; full: boolean; remaining: number | null };
  retention?: MemoryRetentionStatus;
  semanticConflict?: MemorySemanticStatus;
  error?: string;
}

export interface MemoryExportDocument {
  schema: string;
  version: number;
  exportedAt: string;
  sourceDatabase?: string;
  counts: { memories: number; suggestions: number };
  memories: Array<Record<string, unknown>>;
  suggestions: Array<Record<string, unknown>>;
}

export interface MemoryDatabaseHealth {
  ok: boolean;
  path: string;
  integrity?: string;
  foreignKeyViolations?: number;
  pageCount?: number;
  freePages?: number;
  freeRatio?: number;
  error?: string;
}

export interface CorrectionRecord {
  id: string;
  runId: string | null;
  memoryId: string | null;
  subject: string | null;
  wrong: string;
  correction: string;
  providedBy: string;
  scope: string;
  generalizable: boolean;
  status: string;
  createdAt: string;
}

export interface MistakeRecord {
  id: string;
  category: string;
  severity: string;
  runId: string | null;
  skillId: string | null;
  toolName: string | null;
  expected: string | null;
  actual: string | null;
  correctiveAction: string | null;
  reusable: boolean;
  createdAt: string;
}

// ─── Compact prompt profile (Milestone 1) ───────────────────────────────────

export interface MemoryProfileEntry {
  id: string;
  content: string;
  scope: string;
  section: "user" | "project";
  memoryType: string;
  confidence: number;
  provenance: string;
  lastConfirmedAt: string | null;
  updatedAt: string | null;
}

export interface MemoryProfileSnapshot {
  snapshotId: string;
  generatedAt: string;
  memoryVersion: number;
  userEntries: MemoryProfileEntry[];
  projectEntries: MemoryProfileEntry[];
  selectedIds: string[];
  excluded: Array<{ id: string | null; reason: string }>;
  charCount: number;
  tokenEstimate: number;
  limits: Record<string, number>;
  scopeId: string | null;
}

export interface MemoryProfileHistoryEntry {
  id: string;
  version: number;
  selectedIds: string[];
  charCount: number;
  tokenEstimate: number;
  scopeId: string | null;
  runId: string | null;
  excludedCount: number;
  createdAt: string;
}

export interface MemoryProfileResponse {
  success: boolean;
  snapshot: MemoryProfileSnapshot;
  prompt: string;
  history?: { snapshots: MemoryProfileHistoryEntry[]; latest: MemoryProfileHistoryEntry | null };
}

// ─── Session history search (Milestone 2) ───────────────────────────────────

export interface SessionSearchHit {
  messageId: string;
  runId: string;
  userId: string | null;
  role: string;
  kind: string;
  snippet: string;
  content: string | null;
  createdAt: string;
  score: number | null;
}

export interface SessionSearchResult {
  available: boolean;
  engine: string;
  results: SessionSearchHit[];
  hasMore: boolean;
}

export interface SessionSearchHealth {
  fts5: boolean;
  indexed: number;
  retentionDays: number;
  historyEnabled: boolean;
  indexingEnabled: boolean;
}

export interface SessionOpenResult {
  runId: string;
  messages: SessionSearchHit[];
  truncated: boolean;
}

// ─── Learning review (Milestone 3) ──────────────────────────────────────────

export interface LearningReviewResult {
  reviewId?: string;
  runId: string;
  mode: string;
  outcomes: Array<{
    category: string;
    created: boolean;
    inert: boolean;
    reason?: string;
    payload?: Record<string, unknown>;
  }>;
  modelUsed?: boolean;
  tokenBudget?: number;
  gateApplied?: boolean;
  noLearning?: boolean;
}

export interface LearningReviewRecord {
  id: string;
  runId: string;
  status: string;
  mode: string;
  startedAt: string | null;
  finishedAt: string | null;
  model: string | null;
  inputDigest: string | null;
  result: LearningReviewResult | null;
  error: string | null;
  attempts: number;
  createdAt: string;
}

export interface LearningReviewHealth {
  total: number;
  byStatus: Record<string, number>;
  latest: LearningReviewRecord | null;
  queue: { queued: number; running: number; maxConcurrent: number; timeoutMs: number };
}

// ── Named sessions + profiles (M3/M4) ───────────────────────────────────────

export interface ChatSessionRecord {
  id: string;
  profileId: string | null;
  userId: string | null;
  title: string | null;
  status: string;
  summary: Record<string, unknown> | null;
  sourceSessionId: string | null;
  createdAt: string;
  updatedAt: string;
  lastActivityAt: string | null;
  archivedAt: string | null;
}

export interface MemoryProfileRecord {
  id: string;
  name: string;
  directory: string;
  memoryNamespace: string;
  sessionNamespace: string;
  skillNamespace: string;
  providerNamespace: string;
  promptProfile: string;
  retentionDays: number;
  settings: Record<string, unknown>;
  inherits: string | null;
  inheritsReadOnly: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

// ── Memory providers (M8) ───────────────────────────────────────────────────

export interface MemoryProviderCapabilities {
  search: boolean;
  write: boolean;
  delete: boolean;
  export: boolean;
  readOnly: boolean;
}

export interface MemoryProviderHealthState {
  ok: boolean;
  state: string;
  detail: string | null;
  latencyMs: number | null;
  version: string | null;
}

export interface MemoryProviderInfo {
  name: string;
  version: string | null;
  isNative: boolean;
  capabilities: MemoryProviderCapabilities;
  health: MemoryProviderHealthState;
}

export interface MemoryProviderStatus {
  success: boolean;
  externalEnabled: boolean;
  providerCount: number;
  nativeCount: number;
  externalCount: number;
  available: string[];
  providers: MemoryProviderInfo[];
  note: string;
}

export interface MemoryProviderResult {
  recordId: string;
  content: string;
  scope: string;
  scopeId: string | null;
  memoryType: string;
  provider: string;
  provenance: string;
  verified: boolean;
  confidence: number | null;
  retrievedAt: string | null;
  metadata: Record<string, unknown>;
}

export interface MemoryProviderSearchResponse {
  success: boolean;
  native: {
    provider: string;
    results: MemoryProviderResult[];
    degraded: boolean;
    detail: string | null;
  };
  external: Array<{
    provider: string;
    response: {
      provider: string;
      results: MemoryProviderResult[];
      degraded: boolean;
      detail: string | null;
    };
  }>;
  decisions: Array<Record<string, unknown>>;
}
