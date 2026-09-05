import type { AgentProvider, ChatMessage } from './types';
import { MockProvider } from './mock-provider';

/**
 * Registry of available agent providers (client-safe: no server imports).
 *
 * The first CONFIGURED provider wins; the built-in mock is the last-resort
 * fallback so the UI always works. The OpenAI/Ollama provider runs on the
 * server (it needs the settings vault), so the client reaches it through
 * POST /api/agent/chat.
 */
const providers: AgentProvider[] = [
  {
    id: 'openai-compatible',
    label: 'OpenAI / Ollama',
    isConfigured: () => Boolean(
      process.env.OPENAI_API_KEY ||
      process.env.OLLAMA_BASE_URL ||
      process.env.ANTHROPIC_API_KEY ||
      // Bundled client build cannot read server env; this flag is set at
      // startup (instrumentation) when a real provider is available.
      process.env.NEXT_PUBLIC_LLM_CONFIGURED === '1'
    ),
    // Proxy to the server-side provider (registry + settings vault live there).
    chat: async (messages: ChatMessage[]) => {
      const res = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `chat failed (${res.status})`);
      }
      const data = await res.json();
      return data.content as string;
    },
  },
  new MockProvider(),
];

export function getAgentProvider(): AgentProvider {
  const configured = providers.find((p) => p.isConfigured());
  return configured ?? providers[providers.length - 1];
}

export function listProviders(): AgentProvider[] {
  return providers;
}