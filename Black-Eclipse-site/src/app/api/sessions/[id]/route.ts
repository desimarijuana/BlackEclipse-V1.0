import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { redactSecrets } from "@/lib/harness/errors";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";

export const dynamic = "force-dynamic";

async function forward(path: string, method: string, body?: unknown) {
  const healthy = await ensurePythonRuntime();
  if (!healthy) throw new HarnessRuntimeUnavailable("The Python agent runtime is not available.");
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { "X-Harness-Operator": token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20_000),
  });
  return { status: res.status, payload: await res.json().catch(() => ({})) };
}

function errorResponse(err: unknown, fallback: string) {
  const unavailable = err instanceof HarnessRuntimeUnavailable;
  const message = err instanceof Error ? redactSecrets(err.message) : fallback;
  return NextResponse.json({ error: message }, { status: unavailable ? 503 : 500 });
}

// GET /api/sessions/[id] — one session + its run ids.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const { status, payload } = await forward(`/sessions/${encodeURIComponent(id)}`, "GET");
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "session get failed");
  }
}

// PATCH /api/sessions/[id] — rename / pause / archive / restore.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "session-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  try {
    const { id } = await params;
    const { status, payload } = await forward(`/sessions/${encodeURIComponent(id)}`, "PATCH", await request.json().catch(() => ({})));
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "session update failed");
  }
}

// DELETE /api/sessions/[id]?hard= — archive (default) or remove.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "session-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  try {
    const { id } = await params;
    const hard = new URL(request.url).searchParams.get("hard") === "true";
    const { status, payload } = await forward(`/sessions/${encodeURIComponent(id)}?hard=${hard}`, "DELETE");
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "session delete failed");
  }
}
