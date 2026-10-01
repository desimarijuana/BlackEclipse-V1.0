import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!(await ensurePythonRuntime())) {
    return NextResponse.json({ error: "runtime unavailable" }, { status: 503 });
  }
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}/code/tasks/${encodeURIComponent(id)}/diff`, {
    method: "GET",
    headers: token ? { "X-Harness-Operator": token } : undefined,
    signal: AbortSignal.timeout(30_000),
  });
  const body = await res.json().catch(() => ({}));
  return NextResponse.json(body, { status: res.status });
}
