// ── Response lifecycle model ────────────────────────────────────────────────
// The single typed vocabulary for "what is the agent doing" on the client. The
// Python runtime owns the raw event stream (see docs/chat-ui-audit.md); this
// module is the *client* representation the UI renders, so rendering never has
// to understand raw harness envelopes, registry ids, or error codes.
//
// Nothing here talks to the network — it is pure data + formatting.

/** The coarse lifecycle of one assistant turn. */
export type ResponseStatus =
  | 'queued'
  | 'planning'
  | 'tool_running'
  | 'streaming'
  | 'completed'
  | 'cancelled'
  | 'error';

/** One thing the agent did (a tool call, a retrieval source, or a context note). */
export interface ActivityItem {
  /** Stable id — the tool's `toolCallId` when the runtime provides one. */
  id: string;
  kind: 'tool' | 'retrieval' | 'bounded' | 'recall';
  /** Raw operation name, e.g. `market_get_quote`. Kept for developer detail. */
  name: string;
  /** Human-readable label, e.g. "Retrieving market quote". Safe to display. */
  label: string;
  /** Data category / provider for a retrieval item (e.g. "yfinance"). */
  source?: string;
  status: 'running' | 'completed' | 'failed';
  /** Wall-clock duration when the runtime reports one. Never fabricated. */
  durationMs?: number;
  /** Failure code (`TOOL_ERROR`, `TOOL_FORBIDDEN`, …) — detail, not the label. */
  code?: string;
  /**
   * A short, user-safe result summary when the runtime provides one (e.g. a
   * retrieval source reporting "3 records"). Absent when the backend does not
   * report a result — never inferred.
   */
  summary?: string;
  /**
   * Phase 14: an i18n KEY holding one plain sentence for a refused step
   * ("this task isn't set up to make that kind of change"). The raw code stays in
   * `code`. Absent for an ordinary tool step — the component shows `label` then.
   */
  reasonKey?: import('@/lib/i18n/types').TranslationKey;
}

/** A recoverable failure attached to an assistant turn. */
export interface TurnError {
  code?: string;
  message: string;
}

/** The full state of one in-flight or finished assistant turn. */
export interface AssistantTurn {
  status: ResponseStatus;
  /** Prose accumulated from streamed deltas (the live view). */
  text: string;
  /** Authoritative final text from `client.final` when it arrives. */
  finalText?: string;
  activities: ActivityItem[];
  error?: TurnError;
  /**
   * Phase 4 evidence-grounded research metadata carried on `client.final` for a
   * gated run. `undefined` for ordinary chat. Typed loosely here to keep the
   * client model free of a harness-runtime dependency; the chat surface narrows
   * it via `ResearchRunInfo`.
   */
  research?: unknown;
  /**
   * Phase 3-M Reliability: explicit memory-intent outcome + learning-eligibility
   * for an ordinary chat run. `undefined` when the turn had no memory action and
   * the eligibility metadata is absent. Typed loosely to keep the client model
   * free of a harness-runtime dependency.
   */
  memory?: unknown;
  /**
   * The harness run id for this turn. Carried so the chat surface can offer the
   * explicit "Learn from this run" action and read run-scoped diagnostics
   * (eligibility, events) from the originating turn.
   */
  runId?: string;
  /**
   * Phase 14: the run's code-verification ledger, present when the turn used the
   * code capability. Typed loosely to keep this model free of a harness-runtime
   * dependency; the chat surface narrows it via `coerceCodeVerification`.
   */
  codeVerification?: unknown;
  /** Phase 14: the narrow profile the turn was bound to (`plan_only` | `edit_verify`). */
  autonomy?: string | null;
  /** Phase 14 §6.4: the runtime-derived chat capability view. */
  capability?: unknown;
  /** True once a terminal state has been reached. */
  done: boolean;
}

export function emptyTurn(): AssistantTurn {
  return { status: 'queued', text: '', activities: [], done: false };
}

/** The text the UI should show: authoritative final text wins over deltas. */
export function turnText(turn: AssistantTurn): string {
  return turn.finalText && turn.finalText.length > 0 ? turn.finalText : turn.text;
}

const TERMINAL: ReadonlySet<ResponseStatus> = new Set(['completed', 'cancelled', 'error']);

export function isTerminal(status: ResponseStatus): boolean {
  return TERMINAL.has(status);
}

// ── Human labels ─────────────────────────────────────────────────────────────
// Registry ids are snake_case (`market_get_quote`) and retrieval source names
// are lowercase (`yfinance`). Neither is fit to show a user. This map is the
// one place a raw operation name becomes human language.

const TOOL_LABELS: Record<string, string> = {
  market_get_quote: 'Retrieving market quote',
  market_get_ohlcv: 'Retrieving price history',
  fundamentals_get_company_profile: 'Retrieving company profile',
  fundamentals_get_financials: 'Retrieving financial statements',
  research_search: 'Searching research sources',
  research_retrieve_source: 'Reading a research source',
  research_search_news: 'Searching current news',
  macro_get_series: 'Retrieving macro series',
  search_web: 'Searching the web',
  web_search: 'Searching the web',
  web_fetch: 'Reading a web page',
  get_stock_price: 'Retrieving stock price',
  get_stock_fundamentals: 'Retrieving fundamentals',
  get_company_news: 'Retrieving company news',
  calculate_rsi: 'Calculating RSI',
  calculate_sma: 'Calculating moving average',
  calculate_technical_indicators: 'Calculating technical indicators',
  // Repository navigation (read) and authoring (write) — plain job names, never
  // the mechanism. The durable copy lives in the i18n dictionary; this map is
  // the codebase's single place a raw operation id becomes human language.
  workspace_status: 'Checking the project',
  workspace_list: 'Listing the project',
  workspace_search: 'Searching the project',
  workspace_read: 'Reading a file',
  workspace_docs: 'Looking through the notes',
  workspace_patch_apply: 'Writing the change',
  workspace_diff: 'Showing what changed',
  workspace_revert: 'Undoing the change',
};

/** Turn a raw tool name into a short, human label (fallback prettifies it). */
export function toolLabel(name: string): string {
  const known = TOOL_LABELS[name];
  if (known) return known;
  const words = name.replace(/[._]+/g, ' ').trim();
  if (!words) return 'Using a tool';
  return `Using ${words}`;
}

/** Turn a retrieval source name into a display label. */
export function sourceLabel(name: string): string {
  if (!name) return 'source';
  const known: Record<string, string> = {
    jdds: 'market data',
    yfinance: 'Yahoo Finance',
    sec: 'SEC EDGAR',
    web: 'web sources',
    cached: 'cache',
  };
  return known[name.toLowerCase()] ?? name;
}

/**
 * Turn a raw tool name into a short, human label for a *running* tool. This is
 * the label shown on the activity card; `toolLabel` also serves completed
 * items, so the wording stays stable across the transition.
 */
export function toolRunningLabel(name: string): string {
  return toolLabel(name);
}
