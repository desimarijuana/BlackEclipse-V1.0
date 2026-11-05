import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { requireOperatorApiAuth } from "@/lib/auth/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { isAllowedTradingRoute } from "@/lib/harness/trading-routes";

export const dynamic = "force-dynamic";

// ── Broker connectivity proxy (P0, read-only) ─────────────────────────────────
// Paths are allowlisted (`trading-routes.ts`) and every Python `/trading/*`
// route is operator-gated; this proxy injects the runtime operator token, so no
// secret reaches the browser. There is deliberately no order route:
// `/trading/orders` is a 501 in the runtime and is not proxied here.

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "POST" | "PATCH" | "DELETE",
): Promise<Response> {
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
  const target = path.join("/");
  if (!isAllowedTradingRoute(method, path)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported trading route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/trading/${target}`);
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
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `runtime returned ${res.status}`, ...payload },
        { status: res.status },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error(`[api/trading] ${method} ${target} failed:`, err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "broker connectivity unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "trading-connection");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "POST");
}

export async function PATCH(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "trading-connection");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "PATCH");
}

export async function DELETE(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "trading-connection");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "DELETE");
}
