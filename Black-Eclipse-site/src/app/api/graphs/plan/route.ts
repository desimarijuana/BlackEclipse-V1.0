// ── /api/graphs/plan — chat-to-graph ────────────────────────────────────────
// The model credentials are resolved from the settings vault here and sent to
// the Python runtime IN MEMORY. The Python planner validates the proposal
// against the real node registry; this route never saves or executes a graph.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { getLLMConfig } from "@/lib/settings";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const blocked = guardMutation(request, "graph-plan");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const body = (await request.json().catch(() => ({}))) as { objective?: unknown };
  const objective = typeof body.objective === "string" ? body.objective.trim() : "";
  if (!objective) {
    return NextResponse.json({ error: "Describe the workflow you want to build." }, { status: 400 });
  }

  const llm = await getLLMConfig();
  if (!llm || llm.provider === "mock") {
    return NextResponse.json(
      { error: "Chat-to-graph needs a configured model provider. Configure one in Settings." },
      { status: 400 },
    );
  }
  const modelSettings = {
    provider: llm.provider,
    baseUrl: llm.baseUrl,
    apiKey: llm.apiKey,
    model: llm.model,
    contextWindow: llm.contextWindow,
  };

  const token = runtimeCallbackToken();
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/plan`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      body: JSON.stringify({ objective, modelSettings }),
      signal: AbortSignal.timeout(130_000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Graph planning failed" },
      { status: 502 },
    );
  }
}
