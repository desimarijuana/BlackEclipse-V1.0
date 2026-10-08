// ── Agent Workspace — live run stream client ─────────────────────────────────
// Subscribes to the EXISTING runtime SSE transport
// (`GET /api/harness/runs/{id}/stream`) and feeds normalized frames to a
// callback. This is deliberately thin: the same relay the chat uses, no second
// event bus, no second agent loop.
//
// Live runs use this; finished runs replay the persisted trace via
// `GET /api/harness/runs/{id}/events` (see `history.ts`).

import { normalizeWorkspaceEvent } from './normalize';
import type { WorkspaceEvent } from './types';

export interface StreamFrame {
  event: string;
  at: number;
  /** Envelope event id (for dedupe) when the runtime provides one. */
  id?: string;
  /** Envelope sequence (for out-of-order diagnostics) when provided. */
  seq?: number;
}

export interface SubscribeOptions {
  signal: AbortSignal;
  /** Called for every normalized event, in stream order. */
  onEvents: (events: WorkspaceEvent[], frame: StreamFrame) => void;
  /** Called when the stream ends (sentinel / abort / error). */
  onEnd?: (reason: 'end' | 'aborted' | 'error') => void;
}

function sseFrames() {
  let buffer = '';
  return (chunk: string, emit: (event: string, data: Record<string, unknown>) => void) => {
    buffer += chunk;
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = 'message';
      const dataLines: string[] = [];
      for (const line of raw.split('\n')) {
        const clean = line.replace(/\r$/, '');
        if (clean.startsWith('event:')) event = clean.slice(6).trim();
        else if (clean.startsWith('data:')) dataLines.push(clean.slice(5).trim());
      }
      if (dataLines.length === 0) continue;
      try {
        emit(event, JSON.parse(dataLines.join('\n')) as Record<string, unknown>);
      } catch {
        // Ignore a malformed frame rather than killing the stream.
      }
    }
  };
}

/**
 * Stream one run. Returns a promise that resolves when the stream ends. The
 * caller owns the AbortController. Never throws for a normal end/abort.
 */
export async function streamRun(runId: string, options: SubscribeOptions): Promise<void> {
  const { signal, onEvents, onEnd } = options;
  let res: Response;
  try {
    res = await fetch(`/api/harness/runs/${encodeURIComponent(runId)}/stream`, {
      headers: { Accept: 'text/event-stream' },
      signal,
    });
  } catch {
    onEnd?.(signal.aborted ? 'aborted' : 'error');
    return;
  }
  if (!res.ok || !res.body) {
    onEnd?.('error');
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parse = sseFrames();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parse(decoder.decode(value, { stream: true }), (event, data) => {
        if (event === 'stream.end') return;
        const at = Date.now();
        const events = normalizeWorkspaceEvent(event, data, at);
        if (events.length > 0) {
          onEvents(events, {
            event,
            at,
            id: typeof data.id === 'string' ? data.id : undefined,
            seq: typeof data.seq === 'number' ? data.seq : undefined,
          });
        }
      });
    }
    onEnd?.('end');
  } catch {
    onEnd?.(signal.aborted ? 'aborted' : 'error');
  }
}
