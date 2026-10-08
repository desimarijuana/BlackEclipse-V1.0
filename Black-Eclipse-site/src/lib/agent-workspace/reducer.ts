// ── Agent Workspace — normalized state reducer ───────────────────────────────
// A pure, dependency-free reducer that folds NORMALIZED events into an
// `AgentWorkspaceState`. It MUTATES the state it is given (documented as a
// draft): the hook applies it under `immer.produce` so React still gets
// structural sharing, while a batch of 10k events is folded in one pass with no
// array spread per event. Tests call it directly on a fresh initial state.
//
// Bounds (performance): the activity list, artifacts, errors and the dedupe
// maps are all capped so a runaway run cannot grow client memory without limit.
// Large outputs are represented by ArtifactRef handles, never inlined here.

import type {
  ActivityEntry,
  AgentTask,
  AgentWorkspaceState,
  BrowserPatch,
  ComputerPatch,
  ContextPatch,
  ResearchPatch,
  WorkspaceEvent,
} from './types';

const MAX_ACTIVITY = 5_000;
const MAX_ARTIFACTS = 500;
const MAX_ERRORS = 500;
const MAX_CHANGES = 2_000;
/** Trim in chunks when a cap is exceeded, so a hot stream is not O(n) per event. */
const TRIM_SLACK = 512;

/**
 * Enforce a hard cap on a growing list. It only splices once the list has
 * overrun by `TRIM_SLACK`, and then removes the whole overrun at once, so a
 * stream of 10k pushes costs a handful of splices instead of one per event.
 * The list length never exceeds `cap`.
 */
function trimFront<T>(arr: T[], cap: number): void {
  if (arr.length - cap >= TRIM_SLACK) arr.splice(0, arr.length - cap);
}

export function initialWorkspaceState(runId: string | null = null): AgentWorkspaceState {
  return {
    runId,
    execution: { runId, status: 'idle' },
    model: {},
    tasks: [],
    activity: [],
    changes: [],
    artifacts: [],
    permissions: [],
    errors: [],
    context: {
      filesInspected: 0,
      linesInspected: 0,
      toolsUsed: 0,
      researchSources: 0,
      artifacts: 0,
      windowKnown: false,
    },
    contextSources: [],
    telemetry: { toolCalls: 0, toolErrors: 0, retries: 0, costKnown: false },
    seen: {},
    lastSeq: -1,
    outOfOrder: 0,
    seenFiles: {},
    seenTools: {},
  };
}

/** Record a key once. O(1); callers enforce the cap with their own counter. */
function bumpMap(map: Record<string, true>, key: string): boolean {
  if (map[key]) return false;
  map[key] = true;
  return true;
}

/** Fold one normalized event into the draft. Returns the same state. */
export function applyWorkspaceEvent(
  state: AgentWorkspaceState,
  event: WorkspaceEvent,
): AgentWorkspaceState {
  const at = (event as { at?: number }).at ?? Date.now();
  state.execution.updatedAt = at;
  state.telemetry.updatedAt = at;

  switch (event.type) {
    case 'agent': {
      state.execution.status = event.status;
      if (event.phase) state.execution.phase = event.phase;
      if (event.agentId) state.execution.agentId = event.agentId;
      if (event.status === 'running' && state.execution.startedAt == null) {
        state.execution.startedAt = at;
        state.telemetry.startedAt = at;
      }
      break;
    }
    case 'model':
      if (event.provider) state.model.provider = event.provider;
      if (event.model) state.model.model = event.model;
      break;
    case 'model_step': {
      const t = state.telemetry;
      if (event.step != null) {
        t.modelSteps = event.step;
        state.execution.iteration = event.step;
      }
      if (event.promptTokens != null) t.promptTokens = (t.promptTokens ?? 0) + event.promptTokens;
      if (event.completionTokens != null) t.completionTokens = (t.completionTokens ?? 0) + event.completionTokens;
      if (event.totalTokens != null) t.totalTokens = (t.totalTokens ?? 0) + event.totalTokens;
      break;
    }
    case 'plan': {
      event.segments.forEach((title, index) => {
        const id = `plan:${index}`;
        const task: AgentTask = { id, title, status: index === 0 ? 'running' : 'pending' };
        const existing = state.tasks.find((t) => t.id === id);
        if (existing) existing.title = title;
        else state.tasks.push(task);
      });
      break;
    }
    case 'task': {
      const existing = state.tasks.find((t) => t.id === event.id);
      if (existing) {
        existing.status = event.status;
        existing.title = event.title;
        if (event.status === 'running' && existing.startedAt == null) existing.startedAt = at;
        if ((event.status === 'completed' || event.status === 'failed') && existing.completedAt == null) {
          existing.completedAt = at;
        }
      } else {
        state.tasks.push({
          id: event.id,
          title: event.title,
          status: event.status,
          ...(event.status === 'running' ? { startedAt: at } : {}),
        });
      }
      break;
    }
    case 'activity': {
      state.activity.push(event.entry);
      trimFront(state.activity, MAX_ACTIVITY);
      const name = event.entry.name;
      if (name && bumpMap(state.seenTools, event.entry.toolCallId ?? name)) {
        state.context.toolsUsed += 1;
      }
      if (event.entry.status === 'running') state.execution.currentTool = name;
      if (event.entry.status === 'failed') pushError(state, event.entry);
      break;
    }
    case 'activity_end': {
      // LIFO correlation: the most recent running row with the same name.
      let idx = -1;
      for (let i = state.activity.length - 1; i >= 0; i -= 1) {
        const a = state.activity[i];
        if (a.status === 'running' && a.name === event.name) {
          idx = i;
          break;
        }
      }
      if (idx !== -1) {
        const a = state.activity[idx];
        if (state.execution.currentTool === a.name) state.execution.currentTool = undefined;
        a.status = event.status;
        if (event.durationMs != null) a.durationMs = event.durationMs;
        if (event.code) a.code = event.code;
        if (event.summary) a.summary = event.summary;
        if (event.status === 'failed') pushError(state, a);
      } else {
        // Joined mid-run — record a completed row with a unique id.
        const entry: ActivityEntry = {
          id: `end:${event.name}:${at}`,
          category: event.category,
          label: event.name,
          name: event.name,
          status: event.status,
          at,
          durationMs: event.durationMs,
          code: event.code,
          summary: event.summary,
        };
        state.activity.push(entry);
        if (event.status === 'failed') pushError(state, entry);
      }
      if (event.status === 'failed') {
        state.telemetry.toolErrors += 1;
      } else {
        state.telemetry.toolCalls += 1;
      }
      break;
    }
    case 'file': {
      const change = event.change;
      const idx = state.changes.findIndex((c) => c.path === change.path);
      if (idx !== -1) state.changes[idx] = { ...state.changes[idx], ...change };
      else {
        state.changes.push(change);
        trimFront(state.changes, MAX_CHANGES);
      }
      break;
    }
    case 'artifact': {
      if (state.artifacts.some((a) => a.id === event.artifact.id)) break;
      state.artifacts.push(event.artifact);
      trimFront(state.artifacts, MAX_ARTIFACTS);
      state.context.artifacts = state.artifacts.length;
      break;
    }
    case 'permission': {
      const idx = state.permissions.findIndex((p) => p.id === event.permission.id);
      if (idx !== -1) state.permissions[idx] = event.permission;
      else state.permissions.push(event.permission);
      break;
    }
    case 'permission_resolved': {
      for (const permission of state.permissions) {
        if (!event.id || permission.id === event.id) {
          if (permission.status === 'pending') {
            permission.status = event.approved === false ? 'denied' : 'approved';
          }
        }
      }
      break;
    }
    case 'context':
      applyContextPatch(state.context, event.patch);
      if (event.patch.fileKey) {
        if (bumpMap(state.seenFiles, event.patch.fileKey)) {
          state.context.filesInspected = Object.keys(state.seenFiles).length;
        }
      }
      break;
    case 'context_sources':
      state.contextSources = event.sources;
      break;
    case 'research':
      applyResearchPatch(state, event.patch);
      break;
    case 'browser':
      applyBrowserPatch(state, event.patch);
      break;
    case 'computer':
      applyComputerPatch(state, event.patch);
      break;
    case 'error': {
      state.errors.push({
        id: `error:${event.code ?? ''}:${at}`,
        message: event.message,
        code: event.code,
        category: 'error',
        at,
      });
      trimFront(state.errors, MAX_ERRORS);
      if (event.code === 'CONTEXT_RETRY' || event.code === 'REPAIR_ATTEMPT') {
        state.telemetry.retries += 1;
      }
      break;
    }
    case 'finished': {
      state.execution.status = event.status;
      state.telemetry.finishedAt = at;
      break;
    }
  }

  return state;
}

/** Fold a batch in one pass (used by the hook, under one `produce`). */
export function applyWorkspaceEvents(
  state: AgentWorkspaceState,
  events: WorkspaceEvent[],
): AgentWorkspaceState {
  for (const event of events) applyWorkspaceEvent(state, event);
  return state;
}

function pushError(state: AgentWorkspaceState, entry: ActivityEntry): void {
  state.errors.push({
    id: `err:${entry.id}`,
    message: entry.label,
    code: entry.code,
    category: entry.category,
    at: entry.at,
  });
  trimFront(state.errors, MAX_ERRORS);
}

function applyContextPatch(ctx: AgentWorkspaceState['context'], patch: ContextPatch): void {
  if (patch.turnsKept != null) ctx.turnsKept = patch.turnsKept;
  if (patch.turnsDropped != null) ctx.turnsDropped = patch.turnsDropped;
  if (patch.windowTokens !== undefined) ctx.windowTokens = patch.windowTokens;
  if (patch.windowKnown != null) ctx.windowKnown = patch.windowKnown;
  if (patch.droppedTokensEstimate != null) ctx.droppedTokensEstimate = patch.droppedTokensEstimate;
  if (patch.memoriesUsed != null) ctx.memoriesUsed = patch.memoriesUsed;
  if (patch.memoryChars != null) ctx.memoryChars = patch.memoryChars;
  if (patch.linesInspectedDelta) ctx.linesInspected += patch.linesInspectedDelta;
}

function applyResearchPatch(state: AgentWorkspaceState, patch: ResearchPatch): void {
  const r = state.research ?? (state.research = { active: false, sources: 0, queries: 0, claims: 0, conflicts: 0 });
  if (patch.active != null) r.active = patch.active;
  if (patch.query != null) r.query = patch.query;
  if (patch.coverage != null) r.coverage = patch.coverage;
  if (patch.claims != null) r.claims = patch.claims;
  if (patch.conflicts != null) r.conflicts = patch.conflicts;
  if (patch.sourceKey) {
    const keys = r.sourceKeys ?? (r.sourceKeys = {});
    if (bumpMap(keys, patch.sourceKey)) r.sources += 1;
  } else if (patch.sources) {
    r.sources += patch.sources;
  }
  if (patch.queryKey) {
    const keys = r.queryKeys ?? (r.queryKeys = {});
    if (bumpMap(keys, patch.queryKey)) r.queries += 1;
  } else if (patch.queries) {
    r.queries += patch.queries;
  }
  state.context.researchSources = r.sources;
}

function applyBrowserPatch(state: AgentWorkspaceState, patch: BrowserPatch): void {
  const b = state.browser ?? (state.browser = { active: false, actions: 0 });
  if (patch.active != null) b.active = patch.active;
  if (patch.sessionKey) b.sessionId = patch.sessionKey;
  if (patch.sessionId) b.sessionId = patch.sessionId;
  if (patch.url != null) b.url = patch.url;
  if (patch.lastAction != null) {
    b.lastAction = patch.lastAction;
    b.actions += 1;
  }
  if (patch.screenshotRef != null) b.screenshotRef = patch.screenshotRef;
}

function applyComputerPatch(state: AgentWorkspaceState, patch: ComputerPatch): void {
  const c = state.computer ?? (state.computer = { active: false, actions: 0 });
  if (patch.active != null) c.active = patch.active;
  if (patch.sessionKey) c.sessionId = patch.sessionKey;
  if (patch.sessionId) c.sessionId = patch.sessionId;
  if (patch.application != null) c.application = patch.application;
  if (patch.lastAction != null) {
    c.lastAction = patch.lastAction;
    c.actions += 1;
  }
  if (patch.screenshotRef != null) c.screenshotRef = patch.screenshotRef;
}
