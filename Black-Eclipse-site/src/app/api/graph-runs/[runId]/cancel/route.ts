// ── /api/graph-runs/[runId]/cancel — cooperatively cancel a running graph ───

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "graph-run-cancel");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const { runId } = await ctx.params;
  const token = runtimeCallbackToken();
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      signal: AbortSignal.timeout(30_000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to cancel run" },
      { status: 502 },
    );
  }
}
