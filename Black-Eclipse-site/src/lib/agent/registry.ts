import type { AgentProvider, AgentStatusEvent, AgentTool, ChatMessage, ChatOptions } from './types';

/**
 * Registry of agent providers (client-safe: no server imports).
 *
 * Chat is routed through the HARNESS, so the assistant is the Eclipse Agent —
 * system prompt, JDdS tools, persisted run — not a bare completion. The server
 * owns provider configuration (settings vault), so this client layer never
 * decides whether an LLM exists; it forwards and reports the server's answer
 * honestly (a 503 means the runtime is unavailable, never a silently faked
 * reply).
 *
 * The primary path streams: `/api/harness/chat/stream` relays the runtime's SSE
 * events so the UI can show the agent working and writing. If streaming is
 * unavailable (old server, proxy that buffers, runtime spawn failure) it falls
 * back to the one-shot `/api/harness/chat` — a run always produces an answer or
 * an honest error, never a blank.
 */

// Map a raw harness event to a coarse UI status. Kept here (not the route) so
// the labels stay in one place and are reusable by any streaming surface.
export function statusFromEvent(type: string, data: Record<string, unknown> | undefined): AgentStatusEvent | null {
  switch (type) {
    case "run.started":
      return { phase: "starting", label: "Getting ready…", eventType: type };
    case "model.requested":
      return { phase: "thinking", label: "Thinking…", eventType: type };
    case "tool.requested": {
      const tool = typeof data?.name === "string" ? data.name : undefined;
      return { phase: "tool", label: tool ? `Using ${tool}…` : "Using a tool…", eventType: type, tool };
    }
    case "tool.completed": {
      const tool = typeof data?.name === "string" ? data.name : undefined;
      return { phase: "tool", label: tool ? `${tool} done` : "Tool done", eventType: type, tool };
    }
    case "model.delta":
      return { phase: "writing", label: "Writing…", eventType: type };
    case "run.completed":
      return { phase: "done", label: "Done", eventType: type };
    default:
      return null;
  }
}

function buildPayload(messages: ChatMessage[], options?: ChatOptions) {
  const last = [...messages].reverse().find((m) => m.role === 'user');
  const query = last?.content ?? '';
  const history = messages
    .filter((m) => m !== last && (m.role === 'user' || m.role === 'assistant'))
    .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }));
  // The client owns the run id so cancellation is possible while in flight.
  const runId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? `run_${crypto.randomUUID()}`
      : `run_${Date.now().toString(36)}`;
  options?.onRunId?.(runId);
  return { query, history, chatId: options?.chatId, runId };
}

/** One-shot fallback used when SSE is unavailable. */
async function chatOnce(messages: ChatMessage[], options?: ChatOptions): Promise<string> {
  const payload = buildPayload(messages, options);
  const res = await fetch('/api/harness/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Agent run failed (${res.status})`);
  return data.content as string;
}

/**
 * Normalize an SSE frame's payload.
 *
 * Runtime events are emitted as the full envelope (`{ type, data: {...} }`),
 * while the front door's `client.*` events put their fields at the top level.
 * Returning the inner `data` for envelopes keeps consumers reading the same
 * shape regardless of who produced the frame.
 */
export function unwrapEventPayload(data: Record<string, unknown>): Record<string, unknown> {
  const inner = data.data;
  if (inner && typeof inner === "object" && !Array.isArray(inner)) {
    return { ...(inner as Record<string, unknown>), eventType: data.type };
  }
  return data;
}

/**
 * Parse an SSE byte stream into (event, data) frames. Handles partial frames
 * split across reads and the `\r\n` line endings some proxies introduce.
 */
function createSseParser(onFrame: (event: string, data: Record<string, unknown>) => void) {
  let buffer = '';
  return (chunk: string) => {
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
        onFrame(event, JSON.parse(dataLines.join('\n')) as Record<string, unknown>);
      } catch {
        // Ignore a malformed frame rather than killing the stream.
      }
    }
  };
}

async function chatStreaming(messages: ChatMessage[], options?: ChatOptions): Promise<string> {
  const payload = buildPayload(messages, options);
  const res = await fetch('/api/harness/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    // Streaming not available — fall back to the one-shot path.
    return chatOnce(messages, { ...options, onRunId: undefined });
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let assembled = '';
  let finalText: string | null = null;
  let streamError: string | null = null;

  const parse = createSseParser((event, data) => {
    // Runtime events arrive wrapped in the FULL event envelope
    // (`{ id, runId, type, seq, at, data: {...}, transient }`), whereas the
    // front door's own `client.*` events carry their payload at the top level.
    // Unwrap the envelope first — reading `data.text` off the envelope silently
    // yielded "" for every token, so the answer only appeared at the end.
    const payload = unwrapEventPayload(data);
    const status = statusFromEvent(event, payload);
    if (status) options?.onStatus?.(status);
    if (event === 'model.delta') {
      const text = typeof payload.text === 'string' ? payload.text : '';
      if (text) {
        assembled += text;
        options?.onDelta?.(text);
      }
    } else if (event === 'client.final') {
      if (typeof payload.output === 'string') finalText = payload.output;
      if (typeof payload.error === 'string') streamError = payload.error;
      options?.onStatus?.({ phase: 'done', label: 'Done', eventType: event });
    } else if (event === 'client.error') {
      streamError = typeof payload.message === 'string' ? payload.message : 'stream error';
    }
  });

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parse(decoder.decode(value, { stream: true }));
  }

  // Prefer the authoritative final text; fall back to the assembled deltas.
  if (finalText) return finalText;
  if (assembled) return assembled;
  if (streamError) throw new Error(streamError);
  return '';
}

const eclipseAgent: AgentProvider = {
  id: 'eclipse-agent',
  label: 'Eclipse Agent',
  isConfigured: () => true,
  chat: async (messages: ChatMessage[], _tools?: AgentTool[], options?: ChatOptions) => {
    try {
      return await chatStreaming(messages, options);
    } catch (err) {
      // A streaming failure must not lose the run: retry once, one-shot.
      if (options?.onDelta || options?.onStatus) {
        return chatOnce(messages, { ...options, onRunId: undefined });
      }
      throw err;
    }
  },
};

export function getAgentProvider(): AgentProvider {
  return eclipseAgent;
}
