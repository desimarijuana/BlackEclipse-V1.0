import type { AgentProvider, AgentTool, ChatMessage, ChatOptions } from './types';

/**
 * Registry of agent providers (client-safe: no server imports).
 *
 * Chat is routed through the HARNESS (`/api/harness/chat`), so the assistant is
 * the Eclipse Agent — system prompt, JDdS tools, persisted run — not a bare
 * completion. The server owns provider configuration (settings vault), so this
 * client layer never decides whether an LLM exists; it forwards and reports the
 * server's answer honestly (a 503 means the runtime is unavailable, never a
 * silently faked reply).
 */

const eclipseAgent: AgentProvider = {
  id: 'eclipse-agent',
  label: 'Eclipse Agent',
  isConfigured: () => true,
  chat: async (messages: ChatMessage[], _tools?: AgentTool[], options?: ChatOptions) => {
    const last = [...messages].reverse().find((m) => m.role === 'user');
    const query = last?.content ?? '';
    const history = messages
      .filter((m) => m !== last && (m.role === 'user' || m.role === 'assistant'))
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }));

    // The client owns the run id so it can offer cancellation while the run is
    // still in flight — the server never reports a run id early enough for that.
    const runId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? `run_${crypto.randomUUID()}`
        : `run_${Date.now().toString(36)}`;
    options?.onRunId?.(runId);

    const res = await fetch('/api/harness/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, history, chatId: options?.chatId, runId }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // Never fabricate a reply: surface why the run could not happen.
      throw new Error(data.error || `Agent run failed (${res.status})`);
    }
    return data.content as string;
  },
};

export function getAgentProvider(): AgentProvider {
  return eclipseAgent;
}
