// Thin proxy: /api/stats/* -> Python /stats/v1/*.
//
// The Statistical Analysis Engine runs in the Python harness. Next.js validates
// and forwards; the runtime owns all computation. Datasets travel in the request
// body and the engine never reaches a provider or the database, so this is a pure
// computation front door. Nothing here re-implements the statistics.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { redactSecrets } from "@/lib/harness/errors";

export const dynamic = "force-dynamic";

// Feature construction / regime fits can take longer; the Python side bounds it.
const STATS_TIMEOUT_MS = 120_000;

async function forward(request: Request, method: string, path: string[]): Promise<NextResponse> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const url = new URL(request.url);
  const target = `${HARNESS_PY_URL}/stats/v1/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const operatorToken = runtimeCallbackToken();
  const body = method === "GET" ? undefined : await request.text().catch(() => "");
  const res = await fetch(target, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(await runtimeIdentityHeaders(request)),
    },
    body,
    signal: AbortSignal.timeout(STATS_TIMEOUT_MS),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    return NextResponse.json(
      { error: redactSecrets(typeof detail === "string" ? detail : `stats HTTP ${res.status}`), detail },
      { status: res.status },
    );
  }
  return NextResponse.json(payload);
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, ctx: Ctx) {
  try {
    const { path } = await ctx.params;
    return await forward(request, "GET", path);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "stats request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "stats");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { path } = await ctx.params;
    return await forward(request, "POST", path);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "stats request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
