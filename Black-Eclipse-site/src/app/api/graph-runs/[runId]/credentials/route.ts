import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { getLLMConfig } from "@/lib/settings";

export const dynamic = "force-dynamic";

// ── Run-scoped credential re-resolution ──────────────────────────────────────
// A durable graph job can resume in a different process. Model credentials are
// deliberately NOT written into the job payload, so the worker asks the front
// door for the vault's current settings with the operator secret. The response
// is held in the worker's memory for the run only.
//
// This route returns a model key, so it is operator-gated and never cached.

export async function POST(
  request: Request,
  ctx: { params: Promise<{ runId: string }> },
) {
  const blocked = guardMutation(request, "graph-run-credentials");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  const { runId } = await ctx.params;
  if (!runId || runId.length > 200) {
    return NextResponse.json({ error: "runId is required" }, { status: 400 });
  }

  const llm = await getLLMConfig();
  if (!llm || llm.provider === "mock") {
    return NextResponse.json(
      { error: "no model provider is configured; configure one in Settings" },
      { status: 400 },
    );
  }
  return NextResponse.json(
    {
      modelSettings: {
        provider: llm.provider,
        baseUrl: llm.baseUrl,
        apiKey: llm.apiKey,
        model: llm.model,
        contextWindow: llm.contextWindow,
      },
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
