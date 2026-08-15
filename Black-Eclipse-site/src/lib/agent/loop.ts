// Agent loop — runs an LLM with tool-calling until it produces a final answer.
// Provider-agnostic: works with any provider that exposes an OpenAI-compatible
// chat-completions + tool-calling API (OpenAI, Anthropic via gateway, Ollama).

import { getTool, toolSchemas, type ToolDefinition } from "./tools";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  toolCalls?: ToolCall[];
  toolCallId?: string;
}

export interface AgentOptions {
  maxIterations?: number;
  onToolCall?: (call: ToolCall, result: string) => void;
}

export interface AgentResult {
  answer: string;
  toolCalls: number;
  toolErrors: number;
}

/**
 * Run a tool-calling agent loop.
 *
 * The provider is called with the message history + tool schemas. If the model
 * requests tool calls, each is executed and the results are fed back. The loop
 * repeats until the model returns a plain-text answer (no tool calls).
 */
export async function runAgent(
  provider: {
    chat(messages: ChatMessage[], tools: unknown[]): Promise<{ content: string; toolCalls?: ToolCall[] }>;
  },
  systemPrompt: string,
  userQuery: string,
  options: AgentOptions = {}
): Promise<AgentResult> {
  const maxIterations = options.maxIterations ?? 8;
  const messages: ChatMessage[] = [
    { role: "system", content: systemPrompt },
    { role: "user", content: userQuery },
  ];

  let toolCalls = 0;
  let toolErrors = 0;

  for (let i = 0; i < maxIterations; i++) {
    const response = await provider.chat(messages, toolSchemas());

    if (!response.toolCalls || response.toolCalls.length === 0) {
      return { answer: response.content, toolCalls, toolErrors };
    }

    // Append the assistant's tool-call message so the model sees its own calls.
    messages.push({
      role: "assistant",
      content: response.content || "",
      toolCalls: response.toolCalls,
    });

    for (const call of response.toolCalls) {
      toolCalls++;
      const tool: ToolDefinition | undefined = getTool(call.name);
      let result: string;
      try {
        if (!tool) {
          result = `Unknown tool "${call.name}". Available: ${toolSchemas().map((t) => t.function.name).join(", ")}`;
          toolErrors++;
        } else {
          result = await tool.execute(call.arguments || {});
        }
      } catch (err) {
        result = `Tool error: ${err instanceof Error ? err.message : String(err)}`;
        toolErrors++;
      }
      options.onToolCall?.(call, result);
      messages.push({ role: "tool", content: result, toolCallId: call.id });
    }
  }

  return {
    answer: "Reached max iterations without a final answer. Please try a more specific query.",
    toolCalls,
    toolErrors,
  };
}
