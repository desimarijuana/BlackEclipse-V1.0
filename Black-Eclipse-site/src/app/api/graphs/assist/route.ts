// ── /api/graphs/assist — in-editor workflow assistant ──────────────────────
// The model credentials are resolved from the settings vault here and sent to
// the Python runtime IN MEMORY. The Python assistant loops over registry tools
// and validates every proposed operation; this route never saves or executes a
// graph. The editor applies the returned operations through `dispatchMany`.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { getLLMConfig, modelAuthFields } from "@/lib/settings";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const blocked = guardMutation(request, "graph-assist");
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
  const modelSettings = {
    provider: llm.provider,
    baseUrl: llm.baseUrl,
    apiKey: llm.apiKey,
    ...modelAuthFields(llm),
    model: llm.model,
    contextWindow: llm.contextWindow,
  };

  const token = runtimeCallbackToken();
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/assist`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
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
        modelSettings,
      }),
      signal: AbortSignal.timeout(180_000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Workflow assistant failed" },
      { status: 502 },
    );
  }
}
