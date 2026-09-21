import { NextResponse } from "next/server";
import { OpenAICompatibleProvider } from "@/lib/agent/openai-provider";
import { guardExpensiveMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 90;

// POST /api/agent/chat — server-side chat entry point.
// The client registry proxies here when a real LLM (OpenAI / Ollama /
// Anthropic-gateway) is configured; the mock path never leaves the client.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "agent-chat", { limit: 30, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const messages = Array.isArray(body.messages) ? body.messages : null;
    if (!messages || messages.length === 0) {
      return NextResponse.json({ error: "messages are required" }, { status: 400 });
    }
    const provider = new OpenAICompatibleProvider();
    // Check the resolved runtime config (settings vault + env + local servers),
    // not just env — a provider configured in the UI has no env var.
    if (!(await provider.isConfiguredAsync())) {
      return NextResponse.json({ error: "no LLM provider configured" }, { status: 503 });
    }
    const { content } = await provider.chat(messages, []);
    return NextResponse.json({ success: true, content });
  } catch (err) {
    console.error("[api/agent/chat] Error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Chat failed" },
      { status: 500 }
    );
  }
}