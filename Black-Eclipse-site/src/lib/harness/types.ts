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
}

export interface RunResult {
  runId: string;
  status: RunStatus;
  output?: string;
  error?: HarnessErrorJson;
  modelSteps: number;
  toolCalls: number;
  toolErrors: number;
  /** LLM token counts reported by the provider; 0 when it omitted usage. */
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  /** Phase 4 evidence-grounded research metadata, when the run was gated. */
  research?: ResearchRunInfo;
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
  | "coverage"
  | "live_quote"
  | "price_history"
  | "macro_series"
  | "macro_resolve"
  | "web_search"
  | "web_fetch";
