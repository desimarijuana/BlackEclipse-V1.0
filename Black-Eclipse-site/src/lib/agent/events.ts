import type { ActivityItem, PendingApproval, ResponseStatus } from './response-model';
import { sourceLabel, toolLabel } from './response-model';
import { refusalKey } from '@/lib/i18n/refusal-copy';

/**
 * Normalize the harness SSE stream into a small, typed UI event union.
 *
 * This is the ONE place raw harness frames are interpreted. It replaces the
 * ad-hoc `statusFromEvent` mapping so the UI can react to tool failures,
 * retrieval activity, cancellation and errors — not just a generic "Thinking…".
 *
 * Raw shapes (see docs/chat-ui-audit.md §2):
 *  - Runtime events: full envelope `{ id, runId, type, seq, at, data, transient? }`
 *  - Front-door events (`client.*`): payload fields at the top level
 */

export type HarnessUiEvent =
  | { kind: 'status'; status: ResponseStatus }
  | { kind: 'delta'; text: string }
  | { kind: 'activity_start'; item: ActivityItem }
  | {
      kind: 'activity_end';
      id?: string;
      name: string;
      status: 'completed' | 'failed';
      durationMs?: number;
      code?: string;
      /** Short user-safe result summary (e.g. "3 records") when reported. */
      summary?: string;
    }
  | {
      kind: 'final';
      output?: string;
      error?: string;
      errorCode?: string;
      status?: string;
      research?: unknown;
      memory?: unknown;
      runId?: string;
      /** Phase 14: the run's code-verification ledger + code profile, when any. */
      codeVerification?: unknown;
      autonomy?: string | null;
      workspaceId?: string | null;
      /** Phase 14 A6.4: the runtime-derived chat capability view. */
      capability?: unknown;
      /** Vision/Multimodal: the run's collected vision results. */
      vision?: unknown;
      /** Document Intelligence: the run's collected document results. */
      documents?: unknown;
    }
  | { kind: 'error'; message: string; code?: string }
  /** The run is blocked on an operator decision (approval card). */
  | { kind: 'approval_request'; approval: PendingApproval }
  /** A previously requested approval was decided (or expired/timed out). */
  | { kind: 'approval_resolved'; id?: string; approved?: boolean };

/**
 * Normalize a frame's payload.
 *
 * Runtime events are emitted as the full envelope (`{ type, data: {...} }`),
 * while the front door's `client.*` events put their fields at the top level.
 * Returning the inner `data` for envelopes keeps consumers reading the same
 * shape regardless of who produced the frame.
 */
export function unwrapEventPayload(data: Record<string, unknown>): Record<string, unknown> {
  const inner = data.data;
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    return { ...(inner as Record<string, unknown>), eventType: data.type };
  }
  return data;
}

function str(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

const STATUS_BY_EVENT: Record<string, ResponseStatus> = {
  'run.created': 'queued',
  'run.started': 'planning',
  'model.requested': 'planning',
  'model.completed': 'planning',
  'tool.requested': 'tool_running',
  'run.completed': 'completed',
  'run.failed': 'error',
  'run.cancelled': 'cancelled',
};

/**
 * Map one raw `(event, payload)` frame to a typed UI event, or `null` when the
 * frame carries nothing the UI should act on.
 */
export function normalizeHarnessEvent(
  event: string,
  rawPayload: Record<string, unknown>,
): HarnessUiEvent | null {
  const payload = unwrapEventPayload(rawPayload);

  if (event === 'model.delta') {
    const text = str(payload.text) ?? '';
    return text ? { kind: 'delta', text } : null;
  }

  if (event === 'tool.requested') {
    const name = str(payload.name) ?? 'tool';
    const id = str(payload.toolCallId) ?? `tool:${name}`;
    const detail = str(payload.detail);
    return {
      kind: 'activity_start',
      item: {
        id,
        kind: 'tool',
        name,
        label: toolLabel(name),
        status: 'running',
        ...(detail ? { detail } : {}),
      },
    };
  }

  // Context budgeting: the runtime trimmed history to fit the resolved model's
  // window. Surface it as one plain activity line (counts only — never content).
  if (event === 'memory.history_bounded') {
    const dropped = num(payload.droppedTurns) ?? 0;
    const kept = num(payload.keptTurns) ?? 0;
    if (dropped <= 0) return null;
    const windowKnown = payload.windowKnown === true;
    const window = num(payload.window);
    const detail =
      windowKnown && window != null
        ? `${window.toLocaleString()}-token window`
        : 'context window unknown';
    return {
      kind: 'activity_start',
      item: {
        id: 'history_bounded',
        kind: 'bounded',
        name: 'memory.history_bounded',
        label: `Trimmed ${dropped} older turn${dropped === 1 ? '' : 's'} to fit the context window`,
        status: 'completed',
        summary: `${kept} kept · ${detail}`,
      },
    };
  }

  // Memory recall: the runtime injected selected long-term memories into this
  // turn. Surface it as one plain activity line — counts and character budget
  // only, never memory content, ids or excluded text. Mirrors `history_bounded`.
  if (event === 'memory.retrieved') {
    const selected = num(payload.selected) ?? 0;
    if (selected <= 0) return null;
    const usedChars = num(payload.usedChars);
    return {
      kind: 'activity_start',
      item: {
        id: 'memory_recalled',
        kind: 'recall',
        name: 'memory.retrieved',
        label: `Recalled ${selected} memor${selected === 1 ? 'y' : 'ies'} from long-term memory`,
        status: 'completed',
        summary: usedChars != null ? `${usedChars.toLocaleString()} chars recalled` : undefined,
      },
    };
  }

  if (event === 'tool.completed' || event === 'tool.failed') {
    const name = str(payload.name) ?? 'tool';
    const failed = event === 'tool.failed';
    const summary = str(payload.summary);
    return {
      kind: 'activity_end',
      id: str(payload.toolCallId),
      name,
      status: failed ? 'failed' : 'completed',
      durationMs: num(payload.durationMs),
      code: failed ? str(payload.code) : undefined,
      ...(summary ? { summary } : {}),
    };
  }

  // A refused code step (Phase 14): the runtime emits `code.refused` /
  // `code.patch.refused` with a stable code. Show it as ONE plain sentence, not
  // the raw code; the code stays in `code` behind "details". "I couldn't do this
  // and here's exactly why" is a first-class answer.
  if (event === 'code.refused' || event === 'code.patch.refused') {
    const code = str(payload.code) ?? 'REFUSED';
    const tool = str(payload.tool) ?? str(payload.op) ?? 'code';
    // `reasonKey` is always set (the map has a fallback); the component renders
    // it via `useT`, so no locale lives in this reducer. `label`/`name` stay
    // technical and are only shown behind "details".
    return {
      kind: 'activity_start',
      item: {
        id: `code_refused:${code}:${tool}`,
        kind: 'tool',
        name: tool,
        label: toolLabel(tool),
        status: 'completed',
        code,
        reasonKey: refusalKey(code),
      },
    };
  }

  // Retrieval activity — the sources the agent consulted *inside* a tool call.
  if (event === 'retrieval.source_start') {
    const source = str(payload.source) ?? 'source';
    const dataType = str(payload.dataType) ?? '';
    const id = `retrieval:${source}:${dataType}`;
    return {
      kind: 'activity_start',
      item: {
        id,
        kind: 'retrieval',
        name: source,
        label: `Consulting ${sourceLabel(source)}`,
        source,
        status: 'running',
      },
    };
  }

  if (event === 'retrieval.source_ok' || event === 'retrieval.source_unavailable') {
    const source = str(payload.source) ?? 'source';
    const dataType = str(payload.dataType) ?? '';
    const failed = event === 'retrieval.source_unavailable';
    const objects = num(payload.objects);
    return {
      kind: 'activity_end',
      id: `retrieval:${source}:${dataType}`,
      name: source,
      status: failed ? 'failed' : 'completed',
      code: failed ? str(payload.error) : undefined,
      // Only report a count when the runtime actually sent one.
      summary: !failed && objects != null ? `${objects} record${objects === 1 ? '' : 's'}` : undefined,
    };
  }

  // An approval card request (runtime `approval.requested`): the run is now
  // blocked until the operator decides. The legacy `*.approval_required` events
  // are intentionally NOT mapped here — they fire on the deny-and-retry path and
  // the run is not waiting, so surfacing a blocking card would be dishonest.
  if (event === 'approval.requested') {
    const id = str(payload.approvalId);
    if (!id) return null;
    const tool = str(payload.tool) ?? '';
    const title = str(payload.title) ?? (tool ? `Approve using ${tool}` : 'This task requires approval');
    return {
      kind: 'approval_request',
      approval: {
        id,
        kind: str(payload.kind) ?? 'tool',
        title,
        summary: str(payload.summary),
        effect: str(payload.effect),
        risk: str(payload.risk),
        // The "always allow" target: the program/tool and the label the runtime
        // derived. Absent when the action is not grantable (never offered).
        grantPattern: str(payload.grantPattern),
        grantLabel: str(payload.grantLabel),
      },
    };
  }

  if (event === 'approval.resolved') {
    return { kind: 'approval_resolved', id: str(payload.approvalId), approved: payload.approved === true };
  }

  // A standing grant short-circuited the prompt (runtime `approval.granted`).
  // No card is shown; the run proceeds. Surfaced only so the UI can close any
  // stale card for the same step.
  if (event === 'approval.granted') {
    return { kind: 'approval_resolved', approved: true };
  }

  // Front-door terminal frame: carries the authoritative answer.
  if (event === 'client.final') {
    const err = payload.error;
    // `error` is a structured `{ code, message }` from the run record; the
    const errorMessage =
      err && typeof err === 'object'
        ? str((err as Record<string, unknown>).message)
        : str(err);
    const errorCode =
      err && typeof err === 'object' ? str((err as Record<string, unknown>).code) : undefined;
    return {
      kind: 'final',
      output: str(payload.output),
      error: errorMessage,
      errorCode,
      status: str(payload.status),
      research: payload.research ?? undefined,
      memory: payload.memory ?? undefined,
      runId: str(payload.runId),
      codeVerification: payload.codeVerification ?? undefined,
      autonomy: typeof payload.autonomy === 'string' ? payload.autonomy : payload.autonomy === null ? null : undefined,
      workspaceId: typeof payload.workspaceId === 'string' ? payload.workspaceId : payload.workspaceId === null ? null : undefined,
      capability: payload.capability ?? undefined,
      vision: payload.vision ?? undefined,
      documents: payload.documents ?? undefined,
    };
  }

  if (event === 'client.error') {
    return { kind: 'error', message: str(payload.message) ?? 'stream error' };
  }

  if (event === 'run.failed') {
    const error = payload.error;
    const message =
      error && typeof error === 'object'
        ? str((error as Record<string, unknown>).message)
        : undefined;
    const code =
      error && typeof error === 'object' ? str((error as Record<string, unknown>).code) : undefined;
    return { kind: 'error', message: message ?? 'The run failed.', code };
  }

  const status = STATUS_BY_EVENT[event];
  if (status) return { kind: 'status', status };

  return null;
}
