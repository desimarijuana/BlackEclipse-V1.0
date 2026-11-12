import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { redactSecrets } from "@/lib/harness/errors";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";

export const dynamic = "force-dynamic";

// POST /api/sessions/[id]/fork — fork a session.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "session-fork");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  try {
    const { id } = await params;
    const healthy = await ensurePythonRuntime();
    if (!healthy) throw new HarnessRuntimeUnavailable("The Python agent runtime is not available.");
    const token = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/sessions/${encodeURIComponent(id)}/fork`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { "X-Harness-Operator": token } : {}) },
      body: JSON.stringify(await request.json().catch(() => ({}))),
      signal: AbortSignal.timeout(20_000),
    });
    return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const message = err instanceof Error ? redactSecrets(err.message) : "session fork failed";
    return NextResponse.json({ error: message }, { status: unavailable ? 503 : 500 });
  }
}
