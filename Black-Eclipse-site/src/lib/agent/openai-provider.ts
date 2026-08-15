// OpenAI-compatible provider — works with OpenAI, and with Ollama / local
// models via their OpenAI-compatible endpoints. Config via env:
//   OPENAI_API_KEY + OPENAI_BASE_URL (default https://api.openai.com/v1)
//   OPENAI_MODEL (default gpt-4o-mini)
//   OLLAMA_BASE_URL (e.g. http://localhost:11434) + OLLAMA_MODEL
// If OLLAMA_BASE_URL is set, it takes precedence (local, free).

import type { ChatMessage, ToolCall } from "./loop";
import { getLLMConfig } from "@/lib/settings";

interface ChatCompletionResponse {
  choices?: {
    message?: {
      content?: string | null;
      tool_calls?: {
        id: string;
        type: string;
        function: { name: string; arguments: string };
      }[];
    };
  }[];
}

export class OpenAICompatibleProvider {
  readonly id = "openai-compatible";
  readonly label = "OpenAI / Ollama";

  isConfigured(): boolean {
    return Boolean(
      process.env.OPENAI_API_KEY ||
        process.env.OLLAMA_BASE_URL ||
        process.env.ANTHROPIC_API_KEY
    );
  }

  async chat(
    messages: ChatMessage[],
    tools: unknown[]
  ): Promise<{ content: string; toolCalls?: ToolCall[] }> {
    const cfg = await getLLMConfig();
    const baseUrl = cfg.baseUrl.replace(/\/$/, "");
    const apiKey = cfg.apiKey;
    const model = cfg.model;

    const body: Record<string, unknown> = {
      model,
      messages: messages.map((m) => {
        if (m.role === "tool") {
          return { role: "tool", content: m.content, tool_call_id: m.toolCallId };
        }
        if (m.role === "assistant" && m.toolCalls?.length) {
          return {
            role: "assistant",
            content: m.content,
            tool_calls: m.toolCalls.map((tc) => ({
              id: tc.id,
              type: "function",
              function: { name: tc.name, arguments: JSON.stringify(tc.arguments) },
            })),
          };
        }
        return { role: m.role, content: m.content };
      }),
    };
    if (tools && tools.length > 0) body.tools = tools;

    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`LLM request failed (${res.status}): ${text.slice(0, 300)}`);
    }

    const data = (await res.json()) as ChatCompletionResponse;
    const message = data.choices?.[0]?.message;
    const content = message?.content || "";

    const toolCalls: ToolCall[] | undefined = message?.tool_calls?.map((tc) => {
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(tc.function.arguments || "{}");
      } catch {
        args = {};
      }
      return { id: tc.id, name: tc.function.name, arguments: args };
    });

    return { content, toolCalls: toolCalls && toolCalls.length > 0 ? toolCalls : undefined };
  }
}
