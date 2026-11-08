// ── /api/graphs/assist/runs/[runId]/[action] — assistant run controls ────────
// Pause, resume and stop an in-flight workflow-assistant turn. The Python
// runtime owns the run state; these routes are thin operator-authenticated
// proxies, exactly like the graph-run cancel route.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string; action: string }> };

const ACTIONS = new Set(["pause", "resume", "cancel"]);

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "graph-assist-control");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { runId, action } = await ctx.params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: "Unknown assistant control." }, { status: 404 });
  }
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const token = runtimeCallbackToken();
  try {
    const res = await fetch(
      `${HARNESS_PY_URL}/graphs/assist/runs/${encodeURIComponent(runId)}/${action}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-Harness-Operator": token } : {}),
          ...(await runtimeIdentityHeaders(request)),
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `failed to ${action} the assistant run` },
      { status: 502 },
    );
  }
}

export async function GET(request: Request, ctx: Ctx) {
  const { runId, action } = await ctx.params;
  if (action !== "status") {
    return NextResponse.json({ error: "Unknown assistant control." }, { status: 404 });
  }
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const token = runtimeCallbackToken();
  try {
    const res = await fetch(
      `${HARNESS_PY_URL}/graphs/assist/runs/${encodeURIComponent(runId)}`,
      {
        headers: {
          ...(token ? { "X-Harness-Operator": token } : {}),
          ...(await runtimeIdentityHeaders(request)),
        },
        signal: AbortSignal.timeout(15_000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to read the assistant run" },
      { status: 502 },
    );
  }
}
