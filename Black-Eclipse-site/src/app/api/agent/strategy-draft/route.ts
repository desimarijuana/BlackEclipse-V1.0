import { NextResponse } from "next/server";
import { OpenAICompatibleProvider } from "@/lib/agent/openai-provider";
import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  buildDraftMessages,
  extractSpecJson,
  type DraftRequest,
} from "@/lib/strategy-studio/draft-spec";

export const dynamic = "force-dynamic";
export const maxDuration = 90;

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "strategy-draft", { limit: 20, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }

  try {
    const body = (await request.json().catch(() => ({}))) as Partial<DraftRequest>;
    const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
    if (!prompt) {
      return NextResponse.json({ error: "prompt is required" }, { status: 400 });
    }

    const provider = new OpenAICompatibleProvider();
    if (!(await provider.isConfiguredAsync())) {
      return NextResponse.json(
        { error: "No LLM provider configured. Configure a model in Settings first." },
        { status: 503 },
      );
    }

    const input: DraftRequest = {
      prompt,
      symbol: typeof body.symbol === "string" ? body.symbol : undefined,
      timeframe: typeof body.timeframe === "string" ? body.timeframe : undefined,
    };
    const messages = buildDraftMessages(input);
    const first = await provider.chat(messages, []);
    let spec = extractSpecJson(first.content);
    let raw = first.content;

    if (!spec) {
      const repair = await provider.chat(
        [
          ...messages,
          { role: "assistant", content: first.content || "" },
          { role: "user", content: "Your previous reply was not valid JSON. Return one JSON object only, no markdown or prose." },
        ],
        [],
      );
      spec = extractSpecJson(repair.content);
      raw = repair.content;
    }

    if (!spec) {
      return NextResponse.json(
        { error: "The model did not return a parseable strategy spec.", raw: String(raw).slice(0, 4000) },
        { status: 422 },
      );
    }

    return NextResponse.json({ spec, raw: String(raw).slice(0, 20_000) });
  } catch (err) {
    console.error("[api/agent/strategy-draft] Error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Strategy draft failed" },
      { status: 500 },
    );
  }
}
