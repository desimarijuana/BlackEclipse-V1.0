// ── Agent Workspace — event normalizer ───────────────────────────────────────
// Turns ONE raw harness frame into zero or more normalized `WorkspaceEvent`s.
// This is the workspace's single interpretation point; it never touches React
// and never inspects runtime internals beyond the public event contract
// (`{ type, data }` envelope, see docs/harness/architecture.md §"Live streaming").
//
// Safety/contract:
//   * Content-free: only counts, paths, commands, codes and short summaries —
//     never file text, memory text, secrets or hidden reasoning.
//   * Never invents: a field is emitted only when the runtime actually sent it.
//   * Never throws: a malformed frame yields [].

import type {
  ActivityCategory,
  ActivityEntry,
  ContextSource,
  FileChangeKind,
  RunRecordPatch,
  TaskStatus,
  WorkspaceEvent,
} from './types';
import { toolLabel } from '@/lib/agent/response-model';

type Payload = Record<string, unknown>;

function str(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}
function num(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** Unwrap a runtime envelope `{ type, data }` into its inner payload. */
function payloadOf(raw: Payload): Payload {
  const inner = raw.data;
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    return inner as Payload;
  }
  return raw;
}

// ── Category inference ───────────────────────────────────────────────────────

/** Which observable surface a raw tool name belongs to. */
export function toolCategory(name: string): ActivityCategory {
  const n = name.toLowerCase();
  if (n.startsWith('browser_') || n.startsWith('web_browser')) return 'browser';
  if (n.startsWith('computer_')) return 'computer';
  if (n.startsWith('git_') || n.startsWith('vcs_')) return 'git';
  if (
    n.startsWith('research_') ||
    n.startsWith('web_search') ||
    n.startsWith('web_fetch') ||
    n.startsWith('web_') ||
    n.startsWith('search_')
  ) {
    return 'research';
  }
  if (n.startsWith('terminal_') || n.startsWith('shell_') || n === 'command_run') return 'command';
  if (
    n.startsWith('workspace_') ||
    n.startsWith('fs_') ||
    n.startsWith('edit_file') ||
    n.startsWith('patch_') ||
    n.startsWith('write_file') ||
    n.startsWith('read_file')
  ) {
    return 'file';
  }
  return 'tool';
}

/** The category of an explicit `code.*` / `fs.*` / `git.*` event type. */
function eventCategory(type: string): ActivityCategory {
  if (type.startsWith('git.') || type.startsWith('vcs.')) return 'git';
  if (type.startsWith('command.')) return 'command';
  if (type.startsWith('fs.') || type.startsWith('code.') || type.startsWith('workspace.')) return 'file';
  if (type.startsWith('research.') || type.startsWith('webresearch.')) return 'research';
  if (type.startsWith('browser.')) return 'browser';
  if (type.startsWith('computer.')) return 'computer';
  if (type.startsWith('execution.')) return 'artifact';
  if (type.startsWith('approval.') || type.includes('permission')) return 'permission';
  return 'tool';
}

function mapTaskStatus(value: unknown): TaskStatus {
  const s = str(value)?.toLowerCase();
  if (s === 'running' || s === 'in_progress' || s === 'in-progress') return 'running';
  if (s === 'completed' || s === 'done') return 'completed';
  if (s === 'failed' || s === 'error') return 'failed';
  if (s === 'skipped') return 'skipped';
  if (s === 'blocked') return 'blocked';
  return 'pending';
}

function changeKind(value: unknown): FileChangeKind {
  const s = str(value)?.toLowerCase();
  if (s === 'a' || s === 'added' || s === 'add' || s === 'create' || s === 'created' || s === 'copy' || s === 'copied') return 'added';
  if (s === 'd' || s === 'deleted' || s === 'delete' || s === 'remove' || s === 'removed') return 'deleted';
  if (s === 'r' || s === 'renamed' || s === 'rename' || s === 'move' || s === 'moved') return 'renamed';
  return 'modified';
}

/** One per-file change event from a runtime preview record, or null. */
function fileChangeFromPreview(record: Payload, at: number, workspaceId?: string): WorkspaceEvent | null {
  const path = str(record.path) ?? str(record.to);
  if (!path) return null;
  const from = str(record.from);
  const diff = str(record.diff);
  return {
    type: 'file',
    change: {
      path,
      change: changeKind(str(record.op) ?? str(record.operation)),
      additions: num(record.additions),
      deletions: num(record.deletions),
      at,
      ...(workspaceId ? { workspaceId } : {}),
      ...(from ? { from } : {}),
      ...(diff ? { diff } : {}),
      ...(record.diffTruncated === true || record.truncated === true ? { truncated: true } : {}),
    },
  };
}

/** Every per-file change a payload's `previews[]` carries ([] when none). */
function fileChangesFromPayload(p: Payload, at: number, workspaceId?: string): WorkspaceEvent[] {
  const previews = Array.isArray(p.previews) ? (p.previews as Payload[]) : [];
  const out: WorkspaceEvent[] = [];
  for (const preview of previews) {
    if (!preview || typeof preview !== 'object' || Array.isArray(preview)) continue;
    const event = fileChangeFromPreview(preview, at, workspaceId);
    if (event) out.push(event);
  }
  return out;
}

// ── The normalizer ────────────────────────────────────────────────────────────

/** Normalize one raw harness frame. `at` is the frame's epoch-ms timestamp. */
export function normalizeWorkspaceEvent(
  type: string,
  raw: Payload,
  at: number = Date.now(),
): WorkspaceEvent[] {
  const p = payloadOf(raw);
  const out: WorkspaceEvent[] = [];

  switch (type) {
    case 'run.created':
      out.push({ type: 'agent', status: 'idle', at });
      break;
    case 'run.started':
    case 'run.resumed':
      out.push({ type: 'agent', status: 'running', at });
      break;
    case 'run.replanned':
      out.push({ type: 'agent', status: 'planning', at });
      break;
    case 'run.completed':
      out.push({ type: 'finished', status: 'completed', output: str(p.output), at });
      break;
    case 'run.cancelled':
      out.push({ type: 'finished', status: 'cancelled', at });
      break;
    case 'run.failed': {
      const error = p.error;
      const message =
        error && typeof error === 'object'
          ? str((error as Payload).message) ?? 'The run failed.'
          : str(error) ?? 'The run failed.';
      const code =
        error && typeof error === 'object' ? str((error as Payload).code) : undefined;
      out.push({ type: 'error', message, code, at });
      out.push({ type: 'finished', status: 'failed', at });
      break;
    }

    // The front-door terminal frame carries the authoritative run record
    // (provider, model, tokens, steps, context window). The live harness events
    // do not carry all of it (e.g. `model.requested` reports only step/message
    // counts), so folding the record is what fills the Context panel instead of
    // leaving model/provider/window permanently "Not available" after a run.
    case 'client.final': {
      const patch: RunRecordPatch = {};
      const provider = str(p.provider);
      if (provider) patch.provider = provider;
      const model = str(p.model);
      if (model) patch.model = model;
      const promptTokens = num(p.promptTokens);
      if (promptTokens != null) patch.promptTokens = promptTokens;
      const completionTokens = num(p.completionTokens);
      if (completionTokens != null) patch.completionTokens = completionTokens;
      const totalTokens = num(p.totalTokens);
      if (totalTokens != null) patch.totalTokens = totalTokens;
      const modelSteps = num(p.modelSteps);
      if (modelSteps != null) patch.modelSteps = modelSteps;
      const toolCalls = num(p.toolCalls);
      if (toolCalls != null) patch.toolCalls = toolCalls;
      const toolErrors = num(p.toolErrors);
      if (toolErrors != null) patch.toolErrors = toolErrors;

      const context = p.context;
      if (context && typeof context === 'object' && !Array.isArray(context)) {
        const c = context as Payload;
        const window = num(c.window);
        if (window != null && window > 0) patch.windowTokens = window;
        if (c.windowKnown === true) patch.windowKnown = true;
        const keptTurns = num(c.keptTurns);
        if (keptTurns != null) patch.turnsKept = keptTurns;
        const droppedTurns = num(c.droppedTurns);
        if (droppedTurns != null) patch.turnsDropped = droppedTurns;
        const droppedTokensEstimate = num(c.droppedTokensEstimate);
        if (droppedTokensEstimate != null) patch.droppedTokensEstimate = droppedTokensEstimate;
      }

      if (Object.keys(patch).length > 0) out.push({ type: 'run_record', patch, at });
      break;
    }

    case 'model.requested':
      out.push({ type: 'agent', status: 'running', phase: 'planning', at });
      out.push({ type: 'model', provider: str(p.provider), model: str(p.model), at });
      break;
    case 'model.completed':
      out.push({
        type: 'model_step',
        promptTokens: num(p.promptTokens),
        completionTokens: num(p.completionTokens),
        totalTokens: num(p.totalTokens),
        step: num(p.step),
        at,
      });
      break;
    case 'model.routing.completed':
      out.push({ type: 'model', provider: str(p.provider), model: str(p.model), at });
      break;

    case 'prompt.plan': {
      const segments = Array.isArray(p.segments) ? (p.segments as Payload[]) : [];
      const sources: ContextSource[] = [];
      for (const seg of segments) {
        const id = str(seg.id) ?? str(seg.source);
        if (!id) continue;
        sources.push({
          id,
          source: str(seg.source),
          tokens: num(seg.tokenEstimate),
          chars: num(seg.chars),
        });
      }
      if (sources.length > 0) out.push({ type: 'context_sources', sources });
      break;
    }

    // Plans / tasks — the runtime may emit a structured plan or task updates.
    case 'plan.created':
    case 'plan.updated': {
      const tasks = Array.isArray(p.tasks) ? (p.tasks as Payload[]) : [];
      for (const [index, task] of tasks.entries()) {
        const title = str(task.title) ?? str(task.description);
        if (!title) continue;
        out.push({
          type: 'task',
          id: str(task.id) ?? `plan:${index}`,
          title,
          status: mapTaskStatus(task.status),
          at,
        });
      }
      break;
    }
    case 'task.started':
    case 'task.updated':
    case 'task.completed':
    case 'task.failed': {
      const id = str(p.taskId) ?? str(p.id);
      const title = str(p.title) ?? id;
      if (!id || !title) break;
      const fallback: TaskStatus =
        type === 'task.completed' ? 'completed' : type === 'task.failed' ? 'failed' : type === 'task.started' ? 'running' : 'pending';
      out.push({ type: 'task', id, title, status: str(p.status) ? mapTaskStatus(p.status) : fallback, at });
      break;
    }

    case 'code.verify.unverified':
      out.push({ type: 'error', message: 'A check could not be verified', code: str(p.code) ?? 'UNVERIFIED', at });
      break;
    case 'code.repair.exhausted':
      out.push({ type: 'error', message: 'Automatic repair exhausted its budget', code: 'REPAIR_EXHAUSTED', at });
      break;
    case 'code.repair.attempt':
      out.push({ type: 'error', message: 'Repair attempt', code: 'REPAIR_ATTEMPT', at });
      break;

    case 'context.overflow':
      out.push({
        type: 'context',
        patch: { windowKnown: p.windowKnown === true, windowTokens: num(p.window) ?? null },
      });
      break;
    case 'context.retry':
      out.push({ type: 'error', message: 'Context retry', code: 'CONTEXT_RETRY', at });
      break;

    case 'memory.history_bounded':
      out.push({
        type: 'context',
        patch: {
          turnsKept: num(p.keptTurns),
          turnsDropped: num(p.droppedTurns),
          droppedTokensEstimate: num(p.droppedTokensEstimate),
          windowTokens: num(p.window) ?? null,
          windowKnown: p.windowKnown === true,
        },
      });
      break;
    case 'memory.retrieved': {
      const selected = num(p.selected) ?? 0;
      if (selected > 0) {
        out.push({
          type: 'context',
          patch: { memoriesUsed: selected, memoryChars: num(p.usedChars) },
        });
      }
      break;
    }

    case 'tool.requested': {
      const name = str(p.name) ?? 'tool';
      out.push({
        type: 'activity',
        entry: {
          id: str(p.toolCallId) ?? `tool:${name}:${at}`,
          category: toolCategory(name),
          label: toolLabel(name),
          name,
          detail: str(p.detail),
          status: 'running',
          at,
          toolCallId: str(p.toolCallId),
        },
      });
      break;
    }
    case 'tool.completed':
    case 'tool.failed': {
      const name = str(p.name) ?? 'tool';
      out.push({
        type: 'activity_end',
        id: str(p.toolCallId),
        name,
        category: toolCategory(name),
        status: type === 'tool.failed' ? 'failed' : 'completed',
        durationMs: num(p.durationMs),
        code: type === 'tool.failed' ? str(p.code) : undefined,
        summary: str(p.summary),
        at,
      });
      if (p.truncated === true) {
        const total = num(p.totalChars);
        out.push({
          type: 'artifact',
          artifact: {
            id: `truncated:${str(p.toolCallId) ?? name}`,
            name: `${name} output`,
            type: 'terminal',
            createdAt: at,
            sizeBytes: total,
            storageRef: str(p.toolCallId) ?? undefined,
            preview: total != null ? `${total.toLocaleString()} characters` : undefined,
          },
        });
      }
      break;
    }
    case 'tool.truncated':
      out.push({
        type: 'artifact',
        artifact: {
          id: `truncated:${at}`,
          name: 'Truncated output',
          type: 'terminal',
          createdAt: at,
          sizeBytes: num(p.totalChars),
          preview: num(p.shownChars) != null ? `${(num(p.shownChars) as number).toLocaleString()} shown` : undefined,
        },
      });
      break;

    // Refusals / denials — always first-class, never silent.
    case 'code.refused':
    case 'code.patch.refused':
    case 'code.policy.denied':
    case 'code.intel.refused':
    case 'command.refused':
      out.push({
        type: 'activity',
        entry: {
          id: `refused:${type}:${str(p.code) ?? ''}:${at}`,
          category: eventCategory(type),
          label: toolLabel(str(p.tool) ?? str(p.op) ?? 'code'),
          name: str(p.tool) ?? str(p.op),
          detail: str(p.path),
          status: 'completed',
          code: str(p.code),
          at,
        },
      });
      break;
    case 'fs.transaction.rolled_back':
      out.push({ type: 'error', message: 'A change was rolled back', code: str(p.code), at });
      break;

    // Filesystem / code navigation + reads.
    case 'code.read':
      out.push({
        type: 'activity',
        entry: {
          id: `read:${str(p.path) ?? ''}:${at}`,
          category: 'file',
          label: 'Reading a file',
          name: 'code.read',
          detail: str(p.path),
          summary: num(p.lines) != null ? `${num(p.lines)} line(s)` : undefined,
          status: 'completed',
          at,
        },
      });
      if (num(p.lines) != null || str(p.path)) {
        out.push({
          type: 'context',
          patch: { linesInspectedDelta: num(p.lines) ?? 0, fileKey: str(p.path) },
        });
      }
      break;
    case 'code.redacted':
      out.push({
        type: 'activity',
        entry: {
          id: `redacted:${str(p.path) ?? ''}:${at}`,
          category: 'context',
          label: 'Redacted sensitive lines',
          detail: str(p.path),
          summary: num(p.lines) != null ? `${num(p.lines)} line(s)` : undefined,
          status: 'completed',
          at,
        },
      });
      break;
    case 'code.listed':
      out.push({
        type: 'activity',
        entry: {
          id: `listed:${str(p.path) ?? ''}:${at}`,
          category: 'file',
          label: 'Listing the project',
          detail: str(p.path),
          summary: num(p.entries) != null ? `${num(p.entries)} entries` : undefined,
          status: 'completed',
          at,
        },
      });
      break;
    case 'code.searched':
      out.push({
        type: 'activity',
        entry: {
          id: `search:${str(p.pattern) ?? ''}:${at}`,
          category: 'file',
          label: 'Searching the project',
          detail: str(p.pattern),
          summary: num(p.matches) != null ? `${num(p.matches)} matches` : undefined,
          status: 'completed',
          at,
        },
      });
      break;
    case 'code.docs':
      out.push({
        type: 'activity',
        entry: {
          id: `docs:${at}`,
          category: 'file',
          label: 'Looking through the notes',
          status: 'completed',
          at,
        },
      });
      break;

    // Writes → a real change row + an artifact.
    case 'code.write':
    case 'fs.write_file':
    case 'fs.patch_file':
    case 'fs.edit_file.applied': {
      const path = str(p.path) ?? str(p.file);
      const workspaceId = str(p.workspaceId);
      const previews = fileChangesFromPayload(p, at, workspaceId);
      if (previews.length > 0) {
        out.push(...previews);
      } else if (path) {
        out.push({ type: 'file', change: { path, change: 'modified', at, workspaceId } });
      }
      if (path) {
        out.push({
          type: 'artifact',
          artifact: {
            id: `file:${path}:${at}`,
            name: path.split(/[\\/]/).pop() ?? path,
            type: 'code',
            createdAt: at,
            sizeBytes: num(p.bytesWritten) ?? num(p.bytes),
            storageRef: path,
          },
        });
      }
      break;
    }
    case 'code.patch.applied': {
      const path = str(p.path);
      const workspaceId = str(p.workspaceId);
      const preview = fileChangeFromPreview(p, at, workspaceId);
      if (preview) {
        out.push(preview);
      } else if (path) {
        out.push({ type: 'file', change: { path, change: changeKind(p.op), at, workspaceId } });
      }
      out.push({
        type: 'activity',
        entry: {
          id: `patch:${path ?? ''}:${at}`,
          category: 'file',
          label: 'Writing the change',
          name: 'code.patch.applied',
          detail: path,
          summary: str(p.op),
          status: 'completed',
          at,
        },
      });
      break;
    }
    case 'fs.transaction.committed':
      out.push({
        type: 'activity',
        entry: {
          id: `tx:${at}`,
          category: 'file',
          label: 'Saved changes',
          summary: num(p.filesChanged) != null ? `${num(p.filesChanged)} file(s)` : undefined,
          status: 'completed',
          at,
        },
      });
      break;

    case 'code.diff':
    case 'git.diff': {
      const filesChanged = num(p.filesChanged);
      out.push({
        type: 'activity',
        entry: {
          id: `diff:${at}`,
          category: type.startsWith('git') ? 'git' : 'file',
          label: 'Showing what changed',
          summary:
            filesChanged != null
              ? `${filesChanged} file(s) · +${num(p.additions) ?? 0}/-${num(p.deletions) ?? 0}`
              : undefined,
          status: 'completed',
          at,
        },
      });
      out.push({
        type: 'artifact',
        artifact: {
          id: `diff:${str(p.digest) ?? at}`,
          name: 'Diff',
          type: 'diff',
          createdAt: at,
          preview: str(p.digest) ?? undefined,
        },
      });
      break;
    }

    // Terminal / shell commands.
    case 'command.started':
      out.push({
        type: 'activity',
        entry: {
          id: `cmd:${str(p.executionId) ?? str(p.pid) ?? at}`,
          category: 'command',
          label: str(p.commandClass) ? `Running ${str(p.commandClass)}` : 'Running a command',
          name: str(p.program) ?? str(p.commandClass),
          status: 'running',
          at,
        },
      });
      break;
    case 'command.completed':
    case 'command.killed':
      out.push({
        type: 'activity_end',
        id: `cmd:${str(p.executionId) ?? str(p.pid) ?? ''}`,
        name: str(p.commandClass) ?? 'command',
        category: 'command',
        status: p.exitCode === 0 && type === 'command.completed' ? 'completed' : 'failed',
        durationMs: num(p.durationMs),
        summary: num(p.exitCode) != null ? `exit ${num(p.exitCode)}` : undefined,
        at,
      });
      out.push({
        type: 'artifact',
        artifact: {
          id: `term:${str(p.executionId) ?? at}`,
          name: str(p.commandClass) ?? 'Terminal output',
          type: 'terminal',
          createdAt: at,
          storageRef: str(p.executionId) ?? undefined,
        },
      });
      break;
    case 'command.truncated':
      out.push({
        type: 'artifact',
        artifact: {
          id: `cmdtrunc:${at}`,
          name: 'Command output',
          type: 'terminal',
          createdAt: at,
          sizeBytes: num(p.totalChars),
        },
      });
      break;

    // Git.
    case 'git.repository.bound':
      out.push({
        type: 'activity',
        entry: { id: `gitbind:${at}`, category: 'git', label: 'Bound the repository', detail: str(p.repository), summary: str(p.branch), status: 'completed', at },
      });
      break;
    case 'git.status':
      out.push({
        type: 'activity',
        entry: { id: `gitstatus:${at}`, category: 'git', label: 'Checking git status', status: 'completed', at },
      });
      break;
    case 'git.commit':
      out.push({
        type: 'activity',
        entry: {
          id: `gitcommit:${at}`,
          category: 'git',
          label: 'Committing',
          summary: str((p as Payload).commit as string) ?? (p.success === true ? 'committed' : undefined),
          status: p.success === true ? 'completed' : 'failed',
          at,
        },
      });
      break;
    case 'git.action.approved':
      break;
    default:
      break;
  }

  // Generic fall-through for the remaining namespaced families so new runtime
  // events surface as an activity row instead of silently vanishing.
  if (out.length === 0) {
    if (type.startsWith('browser.')) {
      out.push(...browserEvent(type, p, at));
    } else if (type.startsWith('computer.')) {
      out.push(...computerEvent(type, p, at));
    } else if (type.startsWith('research.') || type.startsWith('webresearch.')) {
      out.push(...researchEvent(type, p, at));
    } else if (type.startsWith('execution.')) {
      out.push(...executionEvent(type, p, at));
    } else if (type === 'approval.requested') {
      out.push(...approvalRequested(p, at));
    } else if (type === 'approval.resolved') {
      out.push({ type: 'permission_resolved', id: str(p.approvalId), approved: p.approved === true, at });
    } else if (type === 'retrieval.source_start' || type === 'retrieval.source_ok' || type === 'retrieval.source_unavailable') {
      out.push(...retrievalEvent(type, p, at));
    } else if (type.startsWith('fs.') && Array.isArray(p.previews)) {
      // Every other fs write family (create/delete/apply_diff/multi_file_patch/
      // replace_text/…) reports its change previews in the same shape.
      out.push(...fileChangesFromPayload(p, at, str(p.workspaceId)));
    }
  }

  return out;
}

// ── Family handlers (kept small + isolated) ────────────────────────────────────

function browserEvent(type: string, p: Payload, at: number): WorkspaceEvent[] {
  const sessionId = str(p.sessionId);
  if (type === 'browser.session.created' || type === 'browser.launched') {
    return [{ type: 'browser', patch: { active: true, sessionId, sessionKey: sessionId }, at }];
  }
  if (type === 'browser.session.destroyed' || type === 'browser.closed' || type === 'browser.session.failed') {
    return [{ type: 'browser', patch: { active: false, sessionId }, at }];
  }
  if (type === 'browser.navigated') {
    return [
      { type: 'browser', patch: { active: true, url: str(p.url), lastAction: 'Navigate' }, at },
      activity('browser', 'Browsing', type, str(p.url), at),
    ];
  }
  if (type === 'browser.screenshot') {
    const path = str(p.path);
    return [
      {
        type: 'artifact',
        artifact: {
          id: `shot:${path ?? at}`,
          name: 'Screenshot',
          type: 'image',
          createdAt: at,
          storageRef: path,
        },
      },
      { type: 'browser', patch: { active: true, screenshotRef: path, lastAction: 'Screenshot' }, at },
    ];
  }
  return [{ type: 'browser', patch: { active: true, lastAction: type.replace('browser.', '') }, at }];
}

function computerEvent(type: string, p: Payload, at: number): WorkspaceEvent[] {
  if (type.includes('permission')) {
    return [
      activity('permission', 'Waiting for desktop approval', type, undefined, at, {
        code: str(p.code),
        status: type.includes('denied') ? 'failed' : 'completed',
      }),
    ];
  }
  if (type === 'computer.session.created' || type === 'computer.session.started') {
    return [
      {
        type: 'computer',
        patch: { active: true, sessionId: str(p.sessionId), application: str(p.application) ?? str(p.window) },
        at,
      },
    ];
  }
  if (type === 'computer.session.destroyed') {
    return [{ type: 'computer', patch: { active: false, sessionId: str(p.sessionId) }, at }];
  }
  if (type === 'computer.action') {
    return [
      activity('computer', 'Desktop action', type, str(p.action), at, {
        summary: typeof p.verdict === 'string' ? p.verdict : undefined,
      }),
      { type: 'computer', patch: { active: true, lastAction: str(p.action) }, at },
    ];
  }
  if (type === 'computer.action.failed') {
    return [
      activity('computer', 'Desktop action failed', type, str(p.action), at, {
        code: str(p.code),
        status: 'failed',
      }),
    ];
  }
  return [];
}

function researchEvent(type: string, p: Payload, at: number): WorkspaceEvent[] {
  switch (type) {
    case 'research.started':
    case 'webresearch.started':
      return [{ type: 'research', patch: { active: true }, at }];
    case 'research.web_search':
    case 'webresearch.web_search': {
      const results = num(p.results);
      const query = str(p.query);
      return [
        activity('research', 'Searching the web', type, query, at, {
          summary: results != null ? `${results} result(s)` : undefined,
        }),
        { type: 'research', patch: { active: true, queries: 1, queryKey: query }, at },
      ];
    }
    case 'research.page_fetch':
    case 'webresearch.extracted': {
      const url = str(p.url);
      return [
        activity('research', 'Reading a source', type, url, at),
        { type: 'research', patch: { active: true, sources: 1, sourceKey: url }, at },
      ];
    }
    case 'research.page_fetch_failed':
    case 'webresearch.page_fetch_failed':
      return [activity('research', 'A source was unavailable', type, str(p.url), at, { code: str(p.error), status: 'failed' })];
    case 'research.completed':
    case 'webresearch.completed':
      return [{ type: 'research', patch: { active: false, coverage: str(p.coverage) }, at }];
    case 'research.failed':
      return [activity('research', 'Research failed', type, undefined, at, { status: 'failed' })];
    case 'research.coverage':
      return [{ type: 'research', patch: { coverage: str(p.status) ?? str(p.coverage) }, at }];
    case 'research.validation':
      return [{ type: 'research', patch: { claims: num(p.claims) ?? 0, conflicts: num(p.conflicts) ?? 0 }, at }];
    default:
      return [];
  }
}

function executionEvent(type: string, p: Payload, at: number): WorkspaceEvent[] {
  switch (type) {
    case 'execution.started':
      return [activity('artifact', 'Running the build/check', type, undefined, at, { status: 'running' })];
    case 'execution.test': {
      const passed = p.success === true;
      const results = p.results as Payload | undefined;
      return [
        activity('artifact', 'Running tests', type, undefined, at, {
          status: passed ? 'completed' : 'failed',
          summary:
            results && num(results.passed) != null
              ? `${num(results.passed)} passed · ${num(results.failed) ?? 0} failed`
              : undefined,
        }),
      ];
    }
    case 'execution.build':
      return [activity('artifact', 'Building', type, undefined, at, { status: p.success === true ? 'completed' : 'failed' })];
    case 'execution.completed':
      return [activity('artifact', 'Finished the check', type, undefined, at, { summary: str(p.status), status: 'completed' })];
    case 'execution.failed':
    case 'execution.blocked':
      return [activity('error', 'The check failed', type, undefined, at, { code: str(p.code), status: 'failed' })];
    default:
      return [];
  }
}

function approvalRequested(p: Payload, at: number): WorkspaceEvent[] {
  const id = str(p.approvalId);
  if (!id) return [];
  const tool = str(p.tool) ?? '';
  return [
    {
      type: 'permission',
      permission: {
        id,
        kind: str(p.kind) ?? 'tool',
        title: str(p.title) ?? (tool ? `Approve using ${tool}` : 'This task requires approval'),
        summary: str(p.summary),
        effect: str(p.effect),
        risk: str(p.risk),
        status: 'pending',
        at,
      },
    },
  ];
}

function retrievalEvent(type: string, p: Payload, at: number): WorkspaceEvent[] {
  const source = str(p.source) ?? 'source';
  const dataType = str(p.dataType) ?? '';
  const id = `retrieval:${source}:${dataType}`;
  if (type === 'retrieval.source_start') {
    return [activity('research', `Consulting ${source}`, source, dataType, at, { status: 'running' })];
  }
  const failed = type === 'retrieval.source_unavailable';
  return [
    {
      type: 'activity_end',
      id,
      name: source,
      category: 'research',
      status: failed ? 'failed' : 'completed',
      code: failed ? str(p.error) : undefined,
      summary: !failed && num(p.objects) != null ? `${num(p.objects)} record(s)` : undefined,
      at,
    },
  ];
}

function activity(
  category: ActivityCategory,
  label: string,
  name: string,
  detail: string | undefined,
  at: number,
  extra?: { status?: 'running' | 'completed' | 'failed'; code?: string; summary?: string },
): WorkspaceEvent {
  const entry: ActivityEntry = {
    id: `${name}:${detail ?? ''}:${at}`,
    category,
    label,
    name,
    detail,
    status: extra?.status ?? 'completed',
    at,
    code: extra?.code,
    summary: extra?.summary,
  };
  return { type: 'activity', entry };
}
