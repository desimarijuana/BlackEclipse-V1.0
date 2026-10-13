// ─── Harness TS-side contracts ───────────────────────────────────────────────
// The AGENTIC runtime lives in Python (`python/harness/`) — agents, tools,
// model providers, events and run persistence are all owned there. This file is
// deliberately small: it declares only the shapes the Next.js front door needs
// to (a) proxy HTTP calls to the Python service and (b) read JDdS data for the
// read-only data bridge. There is no run loop, no tool registry and no model
// adapter on this side.

export type RunStatus = "created" | "running" | "completed" | "failed" | "cancelled";

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export interface RunDocument {
  name: string;
  text: string;
}

export interface RunInput {
  query: string;
  ticker?: string;
  market?: string;
  context?: Record<string, unknown>;
  /** Prior turns, oldest first, so a chat follow-up has context. */
  history?: ConversationTurn[];
  /**
   * Extracted text of documents the user attached to this conversation. The
   * front door (not the runtime) performs extraction, because the Python agent
   * has no filesystem access by design.
   */
  documents?: RunDocument[];
}

/**
 * Phase 1 (additive, optional): an optional narrowing/confirmation of the
 * server-resolved workspace root. A caller-supplied `root` must match the root
 * the runtime resolves, otherwise the run gets no workspace. It can never point
 * the runtime at a different directory.
 */
export interface RunWorkspaceRef {
  root: string;
  baseRevision?: string;
}

export interface HarnessErrorJson {
  code: string;
  message: string;
  detail?: string;
}

// ── Phase 4 research metadata (additive, optional) ──────────────────────────
// Present only when a run was routed through the evidence-grounded research
// gate. Absent/undefined for ordinary chat and for older persisted rows, so
// existing clients remain compatible.

export interface ResearchCitation {
  evidenceId: string;
  kind: string;
  source?: string | null;
  sourceType?: string | null;
  url?: string | null;
  title?: string | null;
  publishedAt?: string | null;
  retrievedAt?: string | null;
  validationStatus?: string | null;
  /** Phase 5: issuer-reported fiscal period label, when known. */
  fiscalPeriod?: string | null;
  /** Phase 5: consolidation basis, when explicitly stated. */
  basis?: string | null;
  currency?: string | null;
  unit?: string | null;
  /** Phase 5: the verbatim extraction span, when the fact came from a page. */
  sourceSpan?: string | null;
}

/** A bounded web-escalation audit for a research run. */
export interface ResearchEscalation {
  stages?: string[];
  attempts?: string[];
  notes?: Array<Record<string, unknown>>;
  acceptedEvidence?: number;
  budget?: ResearchBudgetSnapshot | null;
}

export interface ResearchBudgetSnapshot {
  limits: {
    maxSearches: number;
    maxFetches: number;
    maxPages: number;
    maxSeconds: number;
    maxModelTokens: number;
  };
  used: {
    searches: number;
    fetches: number;
    pages: number;
    modelTokens: number;
    elapsedSeconds: number;
  };
  exhausted: string | null;
  attempted: string[];
}

export interface ResearchLimitations {
  limitations: string[];
  missingEvidence: string[];
}

export interface ResearchCoverageLeg {
  legId: string;
  metric: string;
  period?: string | null;
  basis?: string | null;
  status:
    | "covered"
    | "qualified"
    | "conflicting"
    | "unavailable"
    | "unknown"
    | "not_applicable"
    | "no_matching_period"
    | "stale";
  evidenceIds: string[];
  reason?: string | null;
}

export interface ResearchClaim {
  text: string;
  kind: string;
  supportStatus: "supported" | "needs_review" | "unsupported" | "stripped" | "unverified";
  evidenceIds: string[];
  calculationId?: string | null;
  issues: string[];
}

/** Deterministic citation-integrity verdict from the runtime evidence release gate. */
export interface CitationIntegrity {
  status: "ok" | "unverified" | "no_citations" | "no_evidence" | string;
  checked: number;
  verified: number;
  domainKnown?: number;
  unverified: string[];
}

export interface ResearchMetadata {
  taskType: string;
  status: "accepted" | "partial" | "rejected" | string;
  asOf?: string | null;
  citations: ResearchCitation[];
  assumptions: string[];
  estimates: string[];
  interpretations: string[];
  limitations: string[];
  missingEvidence: string[];
  conflicts: Array<Record<string, unknown>>;
  calculations: Array<Record<string, unknown>>;
  /**
   * Ordinary runs only: whether the final answer's cited links were backed by a
   * source this run actually retrieved. Absent on gated research runs (whose
   * claims are validated directly) and on answers that make no citations.
   */
  citationIntegrity?: CitationIntegrity | null;
}

export interface ResearchRunInfo {
  status: "accepted" | "partial" | "rejected" | string;
  metadata?: ResearchMetadata | null;
  receiptAvailable?: boolean;
  persistenceError?: string | null;
  coverage?: { status: string; legs: ResearchCoverageLeg[] } | null;
  validation?: { status: string; claims: ResearchClaim[]; unresolved: string[] } | null;
  receipt?: Record<string, unknown> | null;
  /** Phase 5: what web escalation paths were attempted, and the budget audit. */
  escalation?: ResearchEscalation | null;
  budget?: ResearchBudgetSnapshot | null;
  /**
   * Structured source-route failures (`"{provider} — {category}: {detail}"`),
   * moved OUT of the answer prose so the UI can show them beside the Sources
   * list. Deduplicated, ordered, bounded by the runtime.
   */
  failedRoutes?: string[] | null;
  /** Human-readable reason the loop stopped, when it recorded one. */
  stopReasonText?: string | null;
  /**
   * Phase 8 (WS6/WS7): comparisons the deterministic identity/comparability gate
   * BLOCKED, each with the exact reason. A blocked pair is why a percentage
   * change was not computed; each verified leg is still reported separately.
   */
  blockedComparisons?: BlockedComparison[] | null;
}

export interface BlockedComparison {
  legs: [string, string] | string[];
  dimension: string;
  reason: string;
}

/** One rectangle in image pixel coordinates. */
export interface VisionRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  bbox?: number[];
  label?: string;
}

/** One thing seen in an image, with provenance and a confidence. */
export interface VisionObservation {
  text: string;
  kind?: string;
  method?: string;
  confidence?: number;
  region?: VisionRegion | null;
}

/** One recognized text span (OCR) with its box and confidence. */
export interface VisionTextSpan {
  text: string;
  bounds?: VisionRegion;
  confidence?: number;
}

/** One normalized vision result (mirrors the Python `VisionResult` dict). */
export interface VisionResultInfo {
  ok: boolean;
  mode?: string;
  description?: string;
  assetId?: string | null;
  provider?: string | null;
  model?: string | null;
  backend?: string | null;
  confidence?: number;
  latencyMs?: number;
  cached?: boolean;
  usage?: Record<string, unknown> | null;
  observations?: VisionObservation[];
  text?: VisionTextSpan[];
  tables?: unknown[];
  chart?: Record<string, unknown> | null;
  comparison?: Record<string, unknown> | null;
  document?: Record<string, unknown> | null;
  warnings?: string[];
  provenance?: {
    source?: string | null;
    question?: string | null;
    security?: Record<string, unknown> | null;
    fallback?: boolean | null;
  } | null;
}

/** The run-level vision blob (mirrors `VisionCollector.to_blob()`). */
export interface VisionRunInfo {
  type?: string;
  status: string;
  count: number;
  results: VisionResultInfo[];
  failures?: Array<{ mode?: string; error?: Record<string, unknown> | null }> | null;
}

/** One indexed document in the run's document blob. */
export interface DocumentRunDocument {
  documentId: string;
  kind?: string;
  version?: number;
  title?: string | null;
  fileName?: string | null;
  state?: string;
  /** Per-capability status map, e.g. `{ text: 'PASS', tables: 'PASS', ocr: 'UNAVAILABLE' }`. */
  capabilities?: Record<string, string>;
  pageCount?: number;
  sheetCount?: number;
  confidence?: number;
  textMethod?: string;
  chunkCount?: number;
  tableCount?: number;
  imageCount?: number;
  entityCount?: number;
  evidenceCount?: number;
  currentContext?: { section?: string | null; page?: number | null; path?: string[] } | null;
  pages?: Array<{ index?: number; label?: string; textMethod?: string }>;
  entities?: Array<{ type?: string; value?: string; confidence?: number }>;
  warnings?: string[];
}

/** The run-level document blob (mirrors `DocumentCollector.to_blob()`). */
export interface DocumentRunInfo {
  type?: string;
  status: string;
  count: number;
  documents: DocumentRunDocument[];
  failures?: Array<{ kind?: string; error?: unknown; warnings?: string[] }> | null;
}

/** One normalized internet image result (mirrors the Python `ImageSearchResult`). */
export interface ImageResultInfo {
  id: string;
  imageUrl: string;
  thumbnailUrl?: string | null;
  sourceUrl?: string | null;
  title: string;
  altText?: string | null;
  sourceDomain?: string;
  width?: number | null;
  height?: number | null;
  mimeType?: string | null;
  provider?: string;
  retrievedAt?: string;
  attribution?: string | null;
  validationStatus?: string;
}

/** The run-level internet-image blob (mirrors `ImageCollector.to_blob()`). */
export interface ImagesRunInfo {
  type?: string;
  schemaVersion?: string;
  status: string;
  count: number;
  results: ImageResultInfo[];
  failures?: Array<{ reason?: string }> | null;
}

export interface RunResult {
  runId: string;
  status: RunStatus;
  output?: string;
  error?: HarnessErrorJson;
  /** Phase 1 (additive): the run that spawned this one, when any. */
  parentRunId?: string | null;
  /** Phase 1 (additive): runs this run spawned (e.g. skill invocations). */
  childRunIds?: string[];
  modelSteps: number;
  toolCalls: number;
  toolErrors: number;
  /** LLM token counts reported by the provider; 0 when it omitted usage. */
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  /** Phase 4 evidence-grounded research metadata, when the run was gated. */
  research?: ResearchRunInfo;
  /** Phase 3-M Reliability: explicit memory-intent outcome + learning eligibility. */
  memory?: MemoryRunInfo;
  /**
   * Context budgeting (additive, optional). Present when the runtime trimmed
   * conversation history to fit the resolved model's window. Absent/undefined
   * for older persisted rows and for runs that did not trim, so existing clients
   * remain compatible.
   */
  context?: ContextBudgetInfo;
  /**
   * Phase 4/14 (additive, optional): the run's code-verification ledger. Present
   * for a run that used the code capability (the chat capability panel renders
   * it); absent for ordinary chat and older rows.
   */
  codeVerification?: Record<string, unknown>;
  /** Phase 5 (additive): the autonomy a code run was bound to, when any. */
  autonomy?: string | null;
  /** Phase 5 (additive): the workspace a code run was bound to, when any. */
  workspaceId?: string | null;
  /** Phase 14 (additive): the chat capability view for a coding turn. */
  capability?: Record<string, unknown> | null;
  /**
   * Vision/Multimodal (additive, optional): the run's collected vision results
   * (asset ids, regions, OCR, confidence, provenance). Absent when the run used
   * no vision tool, so existing clients remain compatible.
   */
  vision?: VisionRunInfo | null;
  /**
   * Document Intelligence (additive, optional): the run's collected document
   * results (type, pages, status, capabilities, entities, evidence counts).
   * Absent when the run used no document tool, so existing clients remain
   * compatible.
   */
  documents?: DocumentRunInfo | null;
  /** Internet Image Search (additive, optional): the run's validated image
   *  results, rendered inline by the chat gallery. Absent when no image tool ran. */
  images?: ImagesRunInfo | null;
}

export interface ContextBudgetInfo {
  /** Resolved model context window in tokens, or null when unknown. */
  window: number | null;
  windowKnown: boolean;
  keptTurns: number;
  droppedTurns: number;
  /** Estimated tokens of the dropped window (never the dropped text). */
  droppedTokensEstimate: number;
  /** True when the run recovered from an overflow via the one tighter retry. */
  tighterRetry: boolean;
}

export interface MemoryRunInfo {
  /** saved | forgotten | corrected | refused | needs_confirmation | skill_requested */
  action?: string;
  ok?: boolean;
  refused?: boolean;
  requiresConfirmation?: boolean;
  reason?: string;
  matchedPhrase?: string;
  memoryId?: string;
  memoryType?: string;
  scope?: string;
  subject?: string;
  contentPreview?: string;
  inspectPath?: string;
  undoPath?: string;
  supersededMemoryId?: string;
  archivedMemoryIds?: string[];
  learningEligibility?: {
    eligible: boolean;
    reason: string;
    modelSteps: number;
    toolCalls: number;
    skillRequested: boolean;
    learnQueuePath: string;
    autoCaptured?: boolean;
    skillDraftReady?: boolean;
  };
}

export interface RunRecord {
  id: string;
  agentId: string;
  userId: string | null;
  status: RunStatus;
  input: RunInput;
  output: string | null;
  error: HarnessErrorJson | null;
  modelSteps: number;
  toolCalls: number;
  toolErrors: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  provider: string | null;
  model: string | null;
  /** Phase 4 research metadata (null for ordinary chat / older rows). */
  research?: ResearchRunInfo | null;
  /** Phase 3-M Reliability memory-intent/eligibility (null for older rows). */
  memory?: MemoryRunInfo | null;
  /** Context budgeting metadata (null for ordinary/older rows). */
  context?: ContextBudgetInfo | null;
  /** Phase 4/14: code-verification ledger (null for ordinary/older rows). */
  codeVerification?: Record<string, unknown> | null;
  /** Phase 5: the autonomy a code run was bound to, when any. */
  autonomy?: string | null;
  /** Phase 5: the workspace a code run was bound to, when any. */
  workspaceId?: string | null;
  /** Phase 14: the chat capability view for a coding turn. */
  capability?: Record<string, unknown> | null;
  /** Vision/Multimodal: the run's collected vision results (null otherwise). */
  vision?: VisionRunInfo | null;
  /** Document Intelligence: the run's collected document results (null otherwise). */
  documents?: DocumentRunInfo | null;
  /** Internet Image Search: the run's validated image results (null otherwise). */
  images?: ImagesRunInfo | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

/** One day of token consumption (the analytics chart series). */
export interface UsageDay {
  date: string;
  runs: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

/** Token consumption grouped by the provider/model that served the runs. */
export interface UsageModel {
  provider: string;
  model: string;
  runs: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface UsageRecentRun {
  id: string;
  agentId: string;
  status: RunStatus;
  provider: string | null;
  model: string | null;
  modelSteps: number;
  toolCalls: number;
  toolErrors: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  createdAt: string;
}

/**
 * Token-consumption analytics from the runtime's `agent-memory.db`.
 *
 * `runsWithUsage` is the honesty signal: providers that omit a usage block
 * (e.g. a local Ollama server) contribute 0 tokens while still counting as a
 * run, so the UI can distinguish "no usage reported" from "no activity".
 */
export interface UsageSummary {
  windowDays: number;
  since: string;
  totals: {
    runs: number;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    modelSteps: number;
    toolCalls: number;
    toolErrors: number;
    completed: number;
    failed: number;
    cancelled: number;
    runsWithUsage: number;
  };
  byModel: UsageModel[];
  byDay: UsageDay[];
  recent: UsageRecentRun[];
}

export interface HarnessEvent {
  id: string;
  runId: string;
  type: string;
  seq: number;
  at: string;
  data?: Record<string, unknown>;
}

/**
 * A capability the Python runtime can request over the read-only bridge.
 *
 * `market_snapshot`/`fundamentals`/`news`/`source_health` read JDdS. The Phase-2
 * additions (`live_quote`, `price_history`, `macro_series`, `web_search`,
 * `web_fetch`) are still read-only but reach the existing live providers and the
 * shared web-research transport — they do NOT introduce a second data layer or
 * a second search system.
 */
export type DataCapability =
  | "market_snapshot"
  | "fundamentals"
  | "financial_statements"
  | "sec_filings"
  | "news"
  | "source_health"
  | "research_health"
  | "route_probe"
  | "coverage"
  | "capability_matrix"
  | "provider_key_status"
  | "live_quote"
  | "price_history"
  | "crypto_market_data"
  | "macro_series"
  | "macro_resolve"
  | "web_search"
  | "web_fetch"
  | "academic_search"
  | "news_search"
  | "image_search"
  | "video_search"
  | "playlist_search"
  | "video_metadata"
  | "transcript_fetch"
  | "course_search"
  | "github_search"
  | "mcp_secret_resolve"
  | "mcp_oauth_token_get"
  | "mcp_oauth_token_set"
  | "mcp_oauth_token_clear"
  | "market_data"
  | "market_stream_config"
  | "world_events";
