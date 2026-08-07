import type { AgentProvider } from './types';
import { MockProvider } from './mock-provider';

/**
 * Registry of available agent providers.
 *
 * To add a real provider (OpenAI, Anthropic, Ollama, etc.), implement
 * `AgentProvider` and register it here. The first configured provider wins;
 * otherwise the built-in mock is used.
 */
const providers: AgentProvider[] = [new MockProvider()];

export function getAgentProvider(): AgentProvider {
  const configured = providers.find((p) => p.isConfigured());
  return configured ?? providers[0];
}

export function listProviders(): AgentProvider[] {
  return providers;
}
