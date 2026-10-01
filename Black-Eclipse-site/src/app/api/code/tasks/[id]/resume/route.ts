import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// Probe whether a task can resume (dry, read-only). The actual resume re-enters
// through the run route, which owns CHECKPOINT_NOT_FOUND / RESUME_CONFLICT.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "code-task-resume");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  if (!(await ensurePythonRuntime())) {
    return NextResponse.json({ error: "runtime unavailable" }, { status: 503 });
  }
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}/code/tasks/${encodeURIComponent(id)}/resume`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
    },
    signal: AbortSignal.timeout(30_000),
  });
  const body = await res.json().catch(() => ({}));
  return NextResponse.json(body, { status: res.status });
}
