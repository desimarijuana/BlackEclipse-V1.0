// ─── Eclipse Canvas API proxy ────────────────────────────────────────────────
// A thin pass-through to the Python runtime's /canvas routes. Canvas content
// lives in the ONE artifact catalog; no canvas logic lives here. Mutations pass
// the shared CSRF/origin guard and the runtime identity headers. For AI edit
// proposals the operator's configured model is resolved server-side (the vault
// is not readable from the runtime) and injected as `modelSettings`.

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { guardMutation } from "@/lib/api-guard";
import { resolveRunModelSettings } from "@/lib/harness/run-service";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

async function proxy(request: Request, ctx: Ctx, method: string): Promise<NextResponse> {
  if (method !== "GET") {
    const blocked = guardMutation(request, "canvas");
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
  const target = segments === "" ? "/canvas/artifacts" : `/canvas/${segments}`;
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
    signal: AbortSignal.timeout(120_000),
  };
  if (method !== "GET" && method !== "DELETE") {
    let body = await request.text();
    if (segments.endsWith("/edits") || segments === "artifacts/edits") {
      // Resolve provider/model/credentials from the settings vault. A body that
      // already carries modelSettings is left alone.
      try {
        const parsed = body ? JSON.parse(body) : {};
        if (!parsed.modelSettings) {
          parsed.modelSettings = await resolveRunModelSettings(parsed.model);
          delete parsed.model;
        }
        body = JSON.stringify(parsed);
      } catch {
        return NextResponse.json({ error: "invalid canvas edit request body" }, { status: 400 });
      }
    }
    init.body = body;
  }
  try {
    const res = await fetch(`${HARNESS_PY_URL}${target}${url.search}`, init);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "canvas request failed" },
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
export async function PUT(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "PUT");
}
export async function PATCH(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "PATCH");
}
export async function DELETE(request: Request, ctx: Ctx) {
  return proxy(request, ctx, "DELETE");
}
