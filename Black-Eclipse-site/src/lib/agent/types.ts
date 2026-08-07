/**
 * Agent provider abstraction.
 *
 * BlackEclipse's chat is provider-agnostic: any LLM provider can be plugged
 * in by implementing this interface. Without a configured provider, the app
 * falls back to a built-in mock so the UI always works.
 */

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface AgentTool {
  name: string;
  description: string;
  execute: (args: Record<string, unknown>) => Promise<string>;
}

export interface AgentProvider {
  readonly id: string;
  readonly label: string;
  /** Returns true if this provider is configured (has API key, etc.). */
  isConfigured(): boolean;
  /** Send a chat and get a reply. May use tools. */
  chat(messages: ChatMessage[], tools?: AgentTool[]): Promise<string>;
}
