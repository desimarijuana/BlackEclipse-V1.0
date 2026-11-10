// ─── Large-corpus sources API proxy ──────────────────────────────────────────
// A thin pass-through to the Python runtime's /sources routes. The UI and the
// agent reach the SAME catalog and the same query router; no source logic lives
// here. Adding a root is an operator action, gated by the shared origin guard.

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

async function proxy(request: Request, ctx: Ctx, method: string): Promise<NextResponse> {
  if (method !== "GET") {
    const blocked = guardMutation(request, "sources");
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
  const target = segments === "" ? "/sources" : `/sources/${segments}`;
  const url = new URL(request.url);
  const token = runtimeCallbackToken();
  const user = request.headers.get("x-eclipse-user");
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
      ...(await runtimeIdentityHeaders(request)),
      ...(user ? { "X-Harness-User": user } : {}),
    },
    // A bounded scan/index call can legitimately run for a while, but never
    // forever: the runtime's own budgets are 30–90 s.
    signal: AbortSignal.timeout(120_000),
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
      { error: err instanceof Error ? err.message : "source request failed" },
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
export async function DELETE(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "DELETE");
}
