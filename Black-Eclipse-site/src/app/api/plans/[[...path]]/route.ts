// ─── Plan API proxy ──────────────────────────────────────────────────────────
// A thin pass-through to the Python runtime's /plans routes (the durable Task /
// Plan store). No logic lives here. Mutations pass the shared CSRF/origin guard;
// operator authorization is by transport (loopback) or the runtime token.

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

async function proxy(request: Request, ctx: Ctx, method: string): Promise<NextResponse> {
  if (method !== "GET") {
    const blocked = guardMutation(request, "plans");
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  }
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json(
      { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
      { status: 503 },
    );
  }
  const { path } = await ctx.params;
  const segments = (path ?? []).join("/");
  const target = segments === "" ? "/plans" : `/plans/${segments}`;
  const url = new URL(request.url);
  const token = runtimeCallbackToken();
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
    },
    signal: AbortSignal.timeout(45_000),
  };
  if (method !== "GET" && method !== "DELETE") {
    init.body = await request.text();
  }
  try {
    const res = await fetch(`${HARNESS_PY_URL}${target}${url.search}`, init);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "plan request failed" },
      { status: 502 },
    );
  }
}

export async function GET(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "GET");
}
export async function POST(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "POST");
}
