import type { ActivityItem, ResponseStatus } from './response-model';
import { sourceLabel, toolLabel } from './response-model';

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
  | { kind: 'final'; output?: string; error?: string; errorCode?: string; status?: string; research?: unknown; memory?: unknown; runId?: string }
  | { kind: 'error'; message: string; code?: string };

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
    return {
      kind: 'activity_start',
      item: {
        id,
        kind: 'tool',
        name,
        label: toolLabel(name),
        status: 'running',
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

  if (event === 'tool.completed' || event === 'tool.failed') {
    const name = str(payload.name) ?? 'tool';
    const failed = event === 'tool.failed';
    return {
      kind: 'activity_end',
      id: str(payload.toolCallId),
      name,
      status: failed ? 'failed' : 'completed',
      durationMs: num(payload.durationMs),
      code: failed ? str(payload.code) : undefined,
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

  // Front-door terminal frame: carries the authoritative answer.
  if (event === 'client.final') {
    const err = payload.error;
    // `error` is a structured `{ code, message }` from the run record; the
    // specific code (e.g. CONTEXT_OVERFLOW) must reach the UI, not a generic string.
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
