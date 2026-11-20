// ── /api/graphs/assist/stream — SSE proxy for the workflow assistant ────────
// The Python runtime owns the tool loop and emits `data: {json}` events. This
// route resolves credentials, authenticates the call, and passes the stream
// through without buffering, so the panel can show each tool step live.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { getLLMConfig, modelAuthFields } from "@/lib/settings";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const blocked = guardMutation(request, "graph-assist-stream");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const body = (await request.json().catch(() => ({}))) as {
    instruction?: unknown;
    mode?: unknown;
    ir?: unknown;
    selection?: unknown;
    history?: unknown;
    lastRun?: unknown;
    requireApproval?: unknown;
    model?: unknown;
  };
  const instruction = typeof body.instruction === "string" ? body.instruction.trim() : "";
  if (!instruction) {
    return NextResponse.json({ error: "Type what you want to change." }, { status: 400 });
  }
  if (!body.ir || typeof body.ir !== "object") {
    return NextResponse.json({ error: "The current workflow is missing." }, { status: 400 });
  }

  const llm = await getLLMConfig();
  if (!llm || llm.provider === "mock") {
    return NextResponse.json(
      { error: "The workflow assistant needs a configured model provider. Configure one in Settings." },
      { status: 400 },
    );
  }
  const requestedModel = (body.model && typeof body.model === 'object')
    ? body.model as { provider?: unknown; model?: unknown }
    : null;
  const requestedProvider = typeof requestedModel?.provider === 'string'
    && requestedModel.provider.trim()
    && requestedModel.provider !== 'auto'
    ? requestedModel.provider.trim()
    : null;
  const requestedModelId = typeof requestedModel?.model === 'string' && requestedModel.model.trim()
    ? requestedModel.model.trim()
    : null;
  const modelSettings = {
    provider: requestedProvider ?? llm.provider,
    baseUrl: llm.baseUrl,
    apiKey: llm.apiKey,
    ...modelAuthFields(llm),
    model: requestedModelId ?? llm.model,
    contextWindow: llm.contextWindow,
  };

  const token = runtimeCallbackToken();
  try {
    const upstream = await fetch(`${HARNESS_PY_URL}/graphs/assist/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      body: JSON.stringify({
        instruction,
        mode: body.mode === "ask" ? "ask" : "edit",
        ir: body.ir,
        selection: body.selection ?? null,
        history: Array.isArray(body.history) ? body.history : [],
        lastRun: body.lastRun ?? null,
        requireApproval: body.requireApproval === true,
        modelSettings,
      }),
      signal: request.signal,
    });
    if (!upstream.ok) {
      const data = await upstream.json().catch(() => ({}));
      const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
      return NextResponse.json(
        { error: detail ?? data.error ?? `The workflow assistant failed (${upstream.status})` },
        { status: upstream.status },
      );
    }
    if (!upstream.body) {
      return NextResponse.json({ error: "The assistant returned no stream." }, { status: 502 });
    }
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Workflow assistant failed" },
      { status: 502 },
    );
  }
}
