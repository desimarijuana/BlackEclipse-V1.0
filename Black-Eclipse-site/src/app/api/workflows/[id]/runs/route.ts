// ── /api/workflows/[id]/runs — start a run + list a workflow's runs ─────────
// The TRUST BOUNDARY for graph execution. The IR is loaded from JDDS by the
// persisted workflow id — never taken from the client — and forwarded to the
// Python runtime, which re-validates it and enforces its own permission
// envelope. Phase 3 exposes TEST RUNS only: the runtime refuses any node with a
// write/network/trading side effect, so a test can never act on the world.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { startPersistedRun } from "@/lib/graph-studio/run-server";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

async function runtimeHeaders(request: Request): Promise<Record<string, string>> {
  const token = runtimeCallbackToken();
  const user = request.headers.get("x-eclipse-user");
  return {
    "Content-Type": "application/json",
    ...(token ? { "X-Harness-Operator": token } : {}),
    ...(await runtimeIdentityHeaders(request)),
    ...(user ? { "X-Harness-User": user } : {}),
  };
}

async function runtimeUnavailable(): Promise<NextResponse | null> {
  const healthy = await ensurePythonRuntime();
  if (healthy) return null;
  return NextResponse.json(
    { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
    { status: 503 },
  );
}

export async function GET(request: Request, ctx: Ctx) {
  const unavailable = await runtimeUnavailable();
  if (unavailable) return unavailable;
  const { id } = await ctx.params;
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/runs?workflowId=${encodeURIComponent(id)}&limit=50`, {
      headers: await runtimeHeaders(request),
      signal: AbortSignal.timeout(30_000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to list runs" },
      { status: 502 },
    );
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "workflow-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  const body = (await request.json().catch(() => ({}))) as { version?: number };

  // The persisted version is the ONLY authority for what runs (see run-server).
  const result = await startPersistedRun({
    workflowId: id,
    version: typeof body.version === "number" ? body.version : undefined,
    request,
    testRun: true,
  });
  if (!result.ok) {
    return NextResponse.json(
      result.detail ? { error: result.error, detail: result.detail } : { error: result.error },
      { status: result.status },
    );
  }
  return NextResponse.json({ run: result.run }, { status: result.status });
}
