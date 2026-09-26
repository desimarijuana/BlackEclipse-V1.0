import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { redactSecrets } from "@/lib/harness/errors";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";

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

// GET /api/profiles — list named profiles.
export async function GET() {
  try {
    const { status, payload } = await forward("/profiles", "GET");
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "profile list failed");
  }
}

// POST /api/profiles — create a named profile.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "profile-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  try {
    const { status, payload } = await forward("/profiles", "POST", await request.json().catch(() => ({})));
    return NextResponse.json(payload, { status });
  } catch (err) {
    return errorResponse(err, "profile create failed");
  }
}
