// Thin proxy: /api/research/* -> Python /research/web/*.
//
// The dedicated research screen talks to the Python web-research engine through
// this front door. Next.js validates and forwards; the runtime owns all research
// state. Mutations pass `guardMutation` first, and the operator token is attached
// server-side. Nothing here re-implements research.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { redactSecrets } from "@/lib/harness/errors";

export const dynamic = "force-dynamic";

const RESEARCH_TIMEOUT_MS = 900_000;

async function forward(request: Request, method: string, path: string[]): Promise<NextResponse> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const url = new URL(request.url);
  const target = `${HARNESS_PY_URL}/research/web/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const operatorToken = runtimeCallbackToken();
  const body = method === "GET" || method === "DELETE" ? undefined : await request.text().catch(() => "");
  const res = await fetch(target, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
    },
    body,
    signal: AbortSignal.timeout(RESEARCH_TIMEOUT_MS),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    return NextResponse.json(
      { error: redactSecrets(typeof detail === "string" ? detail : `research HTTP ${res.status}`), detail },
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
      { error: err instanceof Error ? err.message : "research request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "research");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { path } = await ctx.params;
    return await forward(request, "POST", path);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "research request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
