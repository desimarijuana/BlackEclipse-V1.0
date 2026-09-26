import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { redactSecrets } from "@/lib/harness/errors";

export const dynamic = "force-dynamic";

// GET /api/sessions/[id]/export — a bounded portable session export.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const healthy = await ensurePythonRuntime();
    if (!healthy) throw new HarnessRuntimeUnavailable("The Python agent runtime is not available.");
    const token = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/sessions/${encodeURIComponent(id)}/export`, {
      headers: { ...(token ? { "X-Harness-Operator": token } : {}) },
      signal: AbortSignal.timeout(20_000),
    });
    return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const message = err instanceof Error ? redactSecrets(err.message) : "session export failed";
    return NextResponse.json({ error: message }, { status: unavailable ? 503 : 500 });
  }
}
