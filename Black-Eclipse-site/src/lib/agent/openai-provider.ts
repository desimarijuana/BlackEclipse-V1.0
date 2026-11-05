// SERVER-ONLY module: transitively imports the Prisma/SQLite vault via
// @/lib/settings. Never import this from client code — the registry wraps it
// behind a dynamic `import()` instead.

import type { ChatMessage, ToolCall } from "./loop";
import { getLLMConfig } from "@/lib/settings";
import { isLocalBaseUrl } from "./presets";
import { assertModelAllowed } from "@/lib/privacy";

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

  /**
   * Synchronous env-only check. Kept for callers that cannot await; prefer
   * `isConfiguredAsync()`, which also honours the settings vault (a provider
   * configured in the UI has no env var, so this alone would report false).
   */
  isConfigured(): boolean {
    return Boolean(
      process.env.OPENAI_API_KEY ||
        process.env.OLLAMA_BASE_URL ||
        process.env.ANTHROPIC_API_KEY
    );
  }

  /**
   * True when the runtime can actually reach a model: either a key is resolved
   * (vault or env) or the base URL is a keyless local server (Ollama, LM Studio).
   */
  async isConfiguredAsync(): Promise<boolean> {
    try {
      const cfg = await getLLMConfig();
      if (cfg.provider === "mock") return false;
      // Local-only mode must not report a cloud provider as usable.
      try {
        assertModelAllowed(cfg.baseUrl, cfg.provider);
      } catch {
        return false;
      }
      return Boolean(cfg.apiKey) || isLocalBaseUrl(cfg.baseUrl);
    } catch {
      return false;
    }
  }

  async chat(
    messages: ChatMessage[],
    tools: unknown[]
  ): Promise<{ content: string; toolCalls?: ToolCall[] }> {
    const cfg = await getLLMConfig();
    // Local-only mode: refuse before any prompt is serialised or sent.
    assertModelAllowed(cfg.baseUrl, cfg.provider);
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