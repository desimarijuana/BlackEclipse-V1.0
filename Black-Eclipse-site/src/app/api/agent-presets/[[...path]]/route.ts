import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Agent preset proxy ────────────────────────────────────────────────────────
// The Python runtime owns preset storage, tool validation and versioning. This
// front door only validates the mutation, injects the operator token and streams
// the JSON back. A browser never sees the runtime token.

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "POST" | "PATCH" | "DELETE",
): Promise<Response> {
  const target = path.join("/");
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/agents/${target}`);
    const incoming = new URL(request.url);
    incoming.searchParams.forEach((value, key) => url.searchParams.set(key, value));
    const operatorToken = runtimeCallbackToken();
    const identityHeaders = await runtimeIdentityHeaders(request);
    const res = await fetch(url, {
      method,
      headers: {
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        ...identityHeaders,
        ...(method !== "GET" ? { "Content-Type": "application/json" } : {}),
      },
      body: method !== "GET" ? await request.text() : undefined,
      cache: "no-store",
    });
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      const detail = payload.detail;
      return NextResponse.json(
        { error: typeof detail === "string" ? detail : `runtime returned ${res.status}`, ...payload },
        { status: res.status },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error(`[api/agent-presets] ${method} ${target} failed:`, err);
    return NextResponse.json(
      { error: "the agent preset service is unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "agent-preset-write");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "POST");
}

export async function PATCH(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "agent-preset-write");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "PATCH");
}

export async function DELETE(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "agent-preset-write");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "DELETE");
}
