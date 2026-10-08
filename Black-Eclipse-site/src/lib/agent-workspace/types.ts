// ── Agent Workspace — normalized execution-observability model ──────────────
// The client-side vocabulary for "what is the agent doing, right now". The
// Python runtime owns the raw event stream (docs/harness/architecture.md); this
// module is the UI representation the Agent Workspace renders, so no component
// has to understand raw harness envelopes, tool ids or error codes.
//
// Nothing here talks to the network or to React — pure data + formatting.

/** Coarse lifecycle of a run, mirroring the runtime's status vocabulary. */
export type AgentStatus =
  | 'idle'
  | 'planning'
  | 'running'
  | 'waiting'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'blocked';

/** Which observability surface an activity row belongs to. */
export type ActivityCategory =
  | 'plan'
  | 'tool'
  | 'file'
  | 'command'
  | 'git'
  | 'research'
  | 'browser'
  | 'computer'
  | 'artifact'
  | 'permission'
  | 'context'
  | 'model'
  | 'error';

export type ActivityStatus = 'running' | 'completed' | 'failed';

/** One thing the agent did, in chronological order. Content-free by contract. */
export interface ActivityEntry {
  /** Stable id — the runtime's tool call id / event id / a derived composite. */
  id: string;
  category: ActivityCategory;
  /** Human label, safe to display ("Reading a file"). */
  label: string;
  /** Raw operation name for the developer detail line (never the primary copy). */
  name?: string;
  /** What it acted on — a path, command, URL, query. Bounded, content-free. */
  detail?: string;
  status: ActivityStatus;
  /** Epoch ms. */
  at: number;
  durationMs?: number;
  summary?: string;
  /** Failure/refusal code — detail, not the label. */
  code?: string;
  /** Optional handle to a large output or artifact opened in a viewer. */
  outputRef?: string;
  toolCallId?: string;
}

/** One step of the agent's plan / task list. */
export interface AgentTask {
  id: string;
  title: string;
  status: TaskStatus;
  startedAt?: number;
  completedAt?: number;
}

export type FileChangeKind = 'added' | 'modified' | 'deleted' | 'renamed';

export interface FileChange {
  path: string;
  change: FileChangeKind;
  additions?: number;
  deletions?: number;
  at: number;
  /** Run-relative workspace id when the runtime reports one. */
  workspaceId?: string;
}

export type ArtifactType =
  | 'terminal'
  | 'log'
  | 'json'
  | 'text'
  | 'markdown'
  | 'csv'
  | 'code'
  | 'diff'
  | 'image'
  | 'report'
  | 'test'
  | 'other';

/** A large output or produced file, openable in a dedicated viewer. */
export interface ArtifactRef {
  id: string;
  name: string;
  type: ArtifactType;
  mimeType?: string;
  sizeBytes?: number;
  lineCount?: number;
  createdAt: number;
  /** Opaque storage handle (path / url / blob ref) when the runtime gives one. */
  storageRef?: string;
  /** Short preview only — never the full payload. */
  preview?: string;
}

/** A permission/approval the run is blocked on (or a resolved decision). */
export interface PermissionRequest {
  id: string;
  kind: string;
  title: string;
  summary?: string;
  effect?: string;
  risk?: string;
  status: 'pending' | 'approved' | 'denied' | 'expired';
  at: number;
}

/** What context the run is currently using (counts + estimates only). */
export interface ContextUsage {
  turnsKept?: number;
  turnsDropped?: number;
  windowTokens?: number | null;
  windowKnown: boolean;
  droppedTokensEstimate?: number;
  memoriesUsed?: number;
  memoryChars?: number;
  filesInspected: number;
  linesInspected: number;
  toolsUsed: number;
  researchSources: number;
  artifacts: number;
}

export interface RunTelemetry {
  startedAt?: number;
  updatedAt?: number;
  finishedAt?: number;
  modelSteps?: number;
  toolCalls: number;
  toolErrors: number;
  retries: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  /** Provider cost in USD — set only when the runtime actually reports it. */
  costUsd?: number;
  costKnown: boolean;
}

export interface ModelInfo {
  provider?: string;
  model?: string;
}

export interface AgentExecutionState {
  runId: string | null;
  agentId?: string;
  status: AgentStatus;
  phase?: string;
  currentTool?: string;
  iteration?: number;
  maxIterations?: number;
  startedAt?: number;
  updatedAt?: number;
}

/** One segment of the resolved prompt plan — a real "context source". */
export interface ContextSource {
  id: string;
  /** Where the segment comes from (system/instructions/profile/skills/…). */
  source?: string;
  /** Estimated tokens the runtime reported for this segment. */
  tokens?: number;
  chars?: number;
}

export interface ResearchState {
  active: boolean;
  query?: string;
  sources: number;
  queries: number;
  claims: number;
  conflicts: number;
  coverage?: string;
  /** Distinct source keys seen (bounded) so `sources` counts pages, not fetches. */
  sourceKeys?: Record<string, true>;
  /** Distinct query keys seen (bounded). */
  queryKeys?: Record<string, true>;
}

export interface BrowserState {
  active: boolean;
  sessionId?: string;
  url?: string;
  actions: number;
  lastAction?: string;
  screenshotRef?: string;
}

export interface ComputerState {
  active: boolean;
  sessionId?: string;
  application?: string;
  actions: number;
  lastAction?: string;
  screenshotRef?: string;
}

/** A failure the run hit — first-class, linked back to its category. */
export interface WorkspaceError {
  id: string;
  message: string;
  code?: string;
  category: ActivityCategory;
  at: number;
}

/** The full normalized workspace state for one run. */
export interface AgentWorkspaceState {
  runId: string | null;
  execution: AgentExecutionState;
  model: ModelInfo;
  tasks: AgentTask[];
  activity: ActivityEntry[];
  changes: FileChange[];
  artifacts: ArtifactRef[];
  permissions: PermissionRequest[];
  errors: WorkspaceError[];
  context: ContextUsage;
  /** Named prompt segments (the real "context sources", from `prompt.plan`). */
  contextSources: ContextSource[];
  telemetry: RunTelemetry;
  research?: ResearchState;
  browser?: BrowserState;
  computer?: ComputerState;
  /** Event ids already applied — dedupe + out-of-order tolerance. */
  seen: Record<string, true>;
  /** Highest seq observed (for out-of-order detection only, never assumed). */
  lastSeq: number;
  /** Count of events applied out of seq order (diagnostic). */
  outOfOrder: number;
  /** Distinct file paths seen (bounded) — powers `filesInspected`. */
  seenFiles: Record<string, true>;
  /** Distinct tool call ids seen (bounded) — powers `toolsUsed`. */
  seenTools: Record<string, true>;
}

// ── Normalized event union ───────────────────────────────────────────────────
// The workspace consumes NORMALIZED events, not raw envelopes. `normalize.ts`
// produces these; `reducer.ts` applies them. Both are pure.

/** A research patch. Counter fields are INCREMENTS; `sourceKey`/`queryKey`
 *  dedupe within the reducer so fetches to the same URL count once. */
export interface ResearchPatch extends Partial<ResearchState> {
  sourceKey?: string;
  queryKey?: string;
}
export interface BrowserPatch extends Partial<BrowserState> {
  sessionKey?: string;
}
export interface ComputerPatch extends Partial<ComputerState> {
  sessionKey?: string;
}
export interface ContextPatch extends Partial<ContextUsage> {
  /** Increment the inspected-line count (the reducer adds it). */
  linesInspectedDelta?: number;
  /** A file path; the reducer counts only the FIRST time it is seen. */
  fileKey?: string;
}

export type WorkspaceEvent =
  | { type: 'agent'; status: AgentStatus; phase?: string; agentId?: string; at: number }
  | { type: 'model'; provider?: string; model?: string; at: number }
  | { type: 'model_step'; promptTokens?: number; completionTokens?: number; totalTokens?: number; step?: number; at: number }
  | { type: 'plan'; segments: string[]; at: number }
  | { type: 'task'; id: string; title: string; status: TaskStatus; at: number }
  | { type: 'activity'; entry: ActivityEntry }
  | { type: 'activity_end'; id?: string; name: string; category: ActivityCategory; status: 'completed' | 'failed'; durationMs?: number; code?: string; summary?: string; at: number }
  | { type: 'file'; change: FileChange }
  | { type: 'artifact'; artifact: ArtifactRef }
  | { type: 'permission'; permission: PermissionRequest }
  | { type: 'permission_resolved'; id?: string; approved?: boolean; at: number }
  | { type: 'context'; patch: ContextPatch }
  | { type: 'context_sources'; sources: ContextSource[] }
  | { type: 'research'; patch: ResearchPatch; at: number }
  | { type: 'browser'; patch: BrowserPatch; at: number }
  | { type: 'computer'; patch: ComputerPatch; at: number }
  | { type: 'error'; message: string; code?: string; at: number }
  | { type: 'finished'; status: AgentStatus; output?: string; at: number };
