import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { redactSecrets } from "@/lib/harness/errors";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";

export const dynamic = "force-dynamic";

async function forward(path: string, method: string, body?: unknown, operator = false) {
  const healthy = await ensurePythonRuntime();
  if (!healthy) throw new HarnessRuntimeUnavailable("The Python agent runtime is not available.");
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20_000),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok && operator) { /* fall through with the runtime's status */ }
  return { status: res.status, payload };
}

// GET /api/sessions — list named sessions.
export async function GET(request: Request) {
  try {
    const qs = new URL(request.url).searchParams.toString();
    const { status, payload } = await forward(`/sessions?${qs}`, "GET");
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "session list failed");
  }
}

// POST /api/sessions — create a named session.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "session-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  try {
    const { status, payload } = await forward("/sessions", "POST", await request.json().catch(() => ({})), true);
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "session create failed");
  }
}

function errorResponse(err: unknown, fallback: string) {
  const unavailable = err instanceof HarnessRuntimeUnavailable;
  const message = err instanceof Error ? redactSecrets(err.message) : fallback;
  return NextResponse.json({ error: message }, { status: unavailable ? 503 : 500 });
}
