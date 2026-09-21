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

export interface RunInput {
  query: string;
  ticker?: string;
  market?: string;
  context?: Record<string, unknown>;
  /** Prior turns, oldest first, so a chat follow-up has context. */
  history?: ConversationTurn[];
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
  provider: string | null;
  model: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface HarnessEvent {
  id: string;
  runId: string;
  type: string;
  seq: number;
  at: string;
  data?: Record<string, unknown>;
}

/** A JDdS data capability the Python runtime can request over the bridge. */
export type DataCapability =
  | "market_snapshot"
  | "fundamentals"
  | "news"
  | "source_health";
