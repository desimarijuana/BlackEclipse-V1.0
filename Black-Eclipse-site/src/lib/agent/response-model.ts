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
  | 'awaiting_approval'
  | 'completed'
  | 'cancelled'
  | 'error';

/**
 * One action the agent is blocked on until the operator approves or denies it.
 *
 * `id` is the single-use, digest-bound approval row id; approving POSTs a
 * decision that resumes the paused run in place. Carries only display copy the
 * runtime already derived (never file content or secrets).
 */
export interface PendingApproval {
  id: string;
  /** Discriminator, e.g. `mcp_tool`, `code_action`, `terminal_command`. */
  kind: string;
  /** Short imperative title, e.g. "Approve running a command". */
  title: string;
  /** One plain sentence describing exactly what will happen. */
  summary?: string;
  /** Effect class (`write` | `external_action`). */
  effect?: string;
  /** Declared risk (`low` | `medium` | `high`) when the runtime reports one. */
  risk?: string;
  /**
   * The `(kind, scope, pattern)` a "Always allow" choice would remember, e.g.
   * the program `python3` or the MCP tool name. Absent when the runtime did not
   * mark the action grantable — the card then shows no "Always allow" button.
   */
  grantPattern?: string;
  /** Human label for the grant, e.g. "Always allow `python3` in this workspace". */
  grantLabel?: string;
}

/** One thing the agent did (a tool call, a retrieval source, or a context note). */
export interface ActivityItem {
  /** Stable id — the tool's `toolCallId` when the runtime provides one. */
  id: string;
  kind: 'tool' | 'retrieval' | 'bounded' | 'recall';
  /** Raw operation name, e.g. `market_get_quote`. Kept for developer detail. */
  name: string;
  /** Human-readable label, e.g. "Retrieving market quote". Safe to display. */
  label: string;
  /**
   * What the tool is acting on — the command, the file path, or the changed
   * paths. Bounded, content-free (never file text), derived by the runtime's
   * `code/activity.py`. Absent when there is nothing safe to show.
   */
  detail?: string;
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

/**
 * The provider + model that actually served one assistant turn, taken from the
 * run record (never inferred). `provider` is absent when the runtime did not
 * report one; the chat surface then shows the model id alone.
 */
export interface AssistantModel {
  model: string;
  provider?: string | null;
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
   * The provider + model that actually served this turn (from the run record).
   * Absent until `client.final` arrives and for runs that did not report one.
   */
  model?: AssistantModel;
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
  /**
   * Vision/Multimodal: the run's collected vision results (asset ids, regions,
   * OCR, confidence, provenance) for the right sidebar. `undefined` when the
   * turn used no vision tool. Typed loosely to avoid a harness-runtime
   * dependency in this client model; the chat surface narrows it via
   * `coerceVisionRun`.
   */
  vision?: unknown;
  /**
   * Document Intelligence: the run's collected document results (type, pages,
   * status, capabilities, entities, evidence counts). `undefined` when the turn
   * used no document tool; narrowed by the chat surface via `coerceDocumentRun`.
   */
  documents?: unknown;
  /**
   * Internet Image Search: the run's validated, normalized image results
   * (direct image URL, thumbnail, source page, dimensions) for the chat's inline
   * gallery. `undefined` when the turn used no image tool; narrowed by the chat
   * surface via `coerceGalleryBlob`.
   */
  images?: unknown;
  /**
   * A computed result the runtime worked out this turn (`analysis.completed`):
   * outputs, artifacts and provenance. `undefined` when the turn computed
   * nothing; narrowed by the chat surface via `coerceComputedResult`, which
   * renders a provenance-less value as UNAVAILABLE — never as retrieved data.
   */
  analysis?: unknown;
  /**
   * The action the agent is currently blocked on pending an operator decision,
   * or undefined when it is not waiting. Set from `approval.requested`, cleared
   * by `approval.resolved` or the decision POST.
   */
  pendingApproval?: PendingApproval;
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
  command_run: 'Running a check',
  terminal_run: 'Running',
  scaffold_kit: 'Building a tool',
  analysis_run: 'Working it out',
  // Code Intelligence & Understanding Engine (CIUE) — plain job names for the
  // semantic/structural navigation surface. The mechanism (LSP/AST/index) never
  // reaches the user; only the job does.
  code_get_definition: 'Locating the definition',
  code_find_references: 'Finding where it is used',
  code_find_symbol: 'Finding a symbol',
  code_search_symbols: 'Searching symbols',
  code_get_hover: 'Inspecting the type',
  code_get_type: 'Inspecting the type',
  code_get_diagnostics: 'Checking for problems',
  code_get_document_symbols: 'Listing the file structure',
  code_get_callers: 'Finding callers',
  code_get_callees: 'Finding what it calls',
  code_get_call_hierarchy: 'Tracing the call path',
  code_get_implementations: 'Finding implementations',
  code_get_imports: 'Listing imports',
  code_get_exports: 'Listing exports',
  code_get_dependencies: 'Tracing dependencies',
  code_get_dependents: 'Finding dependents',
  code_get_project_structure: 'Mapping the project',
  code_get_dependency_graph: 'Mapping dependencies',
  code_parse_file: 'Reading the file structure',
  code_analyze_file: 'Analysing a file',
  code_rename_symbol: 'Renaming across the project',
  code_organize_imports: 'Reviewing imports',
  code_get_relevant_context: 'Gathering relevant code',
  code_index_workspace: 'Indexing the project',
  code_intel_status: 'Checking code understanding',
  code_find_related_tests: 'Finding related tests',
  // Vision/Multimodal — plain job names. The mechanism (which model / backend)
  // never reaches the user; only the job does.
  vision_analyze: 'Looking at the image',
  image_understand: 'Reading the image',
  vision_answer: 'Looking at the image',
  screenshot_analyze: 'Looking at the screen',
  clipboard_analyze: 'Looking at the clipboard image',
  ocr_extract: 'Reading the text in the image',
  visual_ground: 'Locating an element',
  visual_localize: 'Locating an element',
  chart_analyze: 'Reading the chart',
  document_vision: 'Reading the document',
  visual_compare: 'Comparing the images',
  image_diff: 'Comparing the images',
  screen_compare: 'Comparing the screen',
  image_metadata: 'Inspecting the image',
  vision_capabilities: 'Checking vision support',
  vision_asset_list: 'Listing images',
  vision_remember: 'Remembering a visual observation',
  image_generate: 'Generating an image',
  // Document Intelligence — plain job names.
  document_open: 'Opening the document',
  document_inspect: 'Inspecting the document',
  document_search: 'Searching the document',
  document_extract: 'Reading the document',
  document_analyze: 'Analyzing the document',
  document_query: 'Querying the document data',
  document_compare: 'Comparing the documents',
  document_render: 'Rendering the document',
  document_capabilities: 'Checking document support',
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
