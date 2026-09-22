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
  | "news"
  | "source_health"
  | "coverage"
  | "live_quote"
  | "price_history"
  | "macro_series"
  | "web_search"
  | "web_fetch";
