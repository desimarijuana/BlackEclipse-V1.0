// ─── Portfolio API proxy ─────────────────────────────────────────────────────
// A thin pass-through to the Python runtime's /portfolio routes, so the UI and
// the agent reach the SAME engine. No accounting logic lives here. Mutations
// pass the shared CSRF/origin guard; operator authorization is by transport
// (loopback) or the runtime token, presented to the Python side as a header.

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

async function proxy(request: Request, ctx: Ctx, method: string): Promise<NextResponse> {
  if (method !== "GET") {
    const blocked = guardMutation(request, "portfolio");
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
  const url = new URL(request.url);
  let target: string;
  if (segments === "") {
    if (method === "GET") target = "/portfolio/list";
    else if (method === "POST") target = "/portfolio/create";
    else return NextResponse.json({ error: "method not allowed" }, { status: 405 });
  } else {
    target = `/portfolio/${segments}`;
  }
  const token = runtimeCallbackToken();
  const user = request.headers.get("x-eclipse-user");
  const unlock = request.headers.get("x-eclipse-unlock");
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
      ...(unlock ? { "X-Eclipse-Unlock": unlock } : {}),
      ...(await runtimeIdentityHeaders(request)),
      ...(user ? { "X-Harness-User": user } : {}),
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
      { error: err instanceof Error ? err.message : "portfolio request failed" },
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
export async function PATCH(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "PATCH");
}
export async function DELETE(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "DELETE");
}
