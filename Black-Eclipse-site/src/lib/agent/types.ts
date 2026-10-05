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

/** A live step the agent is taking, surfaced to the UI while a run is in flight. */
export interface AgentStatusEvent {
  /** Coarse phase for the working indicator. */
  phase: "starting" | "thinking" | "tool" | "writing" | "done";
  /** Human-readable label, e.g. "Checking AAPL price…". */
  label: string;
  /** Raw harness event type that produced this. */
  eventType: string;
  /** Tool name, when the phase is `tool`. */
  tool?: string;
}

export interface ChatOptions {
  /**
   * Conversation id. When present the front door loads that conversation's
   * workspace folder as run context and saves the answer back into it.
   */
  chatId?: string;
  /**
   * The model id the operator picked in the composer for THIS turn. Overrides
   * the saved model in the settings vault for the provider already configured
   * (the provider/key are unchanged). Absent = the saved model.
   */
  model?: string;
  /**
   * Called with the harness run id as soon as it is known, so the caller can
   * offer cancellation before the reply arrives.
   */
  onRunId?: (runId: string) => void;
  /** Called with each streamed token fragment as the answer is written. */
  onDelta?: (text: string) => void;
  /** Called with each coarse agent step, so the UI shows it is working. */
  onStatus?: (event: AgentStatusEvent) => void;
  /**
   * Called with each normalized UI event (tool start/end, retrieval activity,
   * final, error, status). Superset of `onDelta`/`onStatus` — the shared
   * `useAgentRun` hook uses this to build the full response lifecycle.
   */
  onEvent?: (event: import('./events').HarnessUiEvent) => void;
  /** Abort the underlying fetch (used by Stop generation). */
  signal?: AbortSignal;
}

export interface AgentProvider {
  readonly id: string;
  readonly label: string;
  /** Returns true if this provider is configured (has API key, etc.). */
  isConfigured(): boolean;
  /** Send a chat and get a reply. May use tools. */
  chat(messages: ChatMessage[], tools?: AgentTool[], options?: ChatOptions): Promise<string>;
}
