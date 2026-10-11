// Thin proxy: /api/research-data/* -> Python /research-data/*.
//
// The Research Data screen talks to the Python research-data API through this
// front door. Next.js validates and forwards; the runtime owns providers,
// verification, transforms and datasets. Mutations pass `guardMutation` first,
// and the operator token is attached server-side. Nothing here re-implements
// the system.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { redactSecrets } from "@/lib/harness/errors";

export const dynamic = "force-dynamic";

// A dataset build/refresh can take a while; the Python side bounds it.
const RESEARCH_DATA_TIMEOUT_MS = 300_000;

async function forward(request: Request, method: string, path: string[]): Promise<NextResponse> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const url = new URL(request.url);
  const target = `${HARNESS_PY_URL}/research-data/${path.map(encodeURIComponent).join("/")}${url.search}`;
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
    signal: AbortSignal.timeout(RESEARCH_DATA_TIMEOUT_MS),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    return NextResponse.json(
      { error: redactSecrets(typeof detail === "string" ? detail : `research-data HTTP ${res.status}`), detail },
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
      { error: err instanceof Error ? err.message : "research-data request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "research-data");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { path } = await ctx.params;
    return await forward(request, "POST", path);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "research-data request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
