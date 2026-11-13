import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Delegation lifecycle proxy (W7) ─────────────────────────────────────────
// Thin pass-through to the Python `/delegations/*` routes. The Python routes
// are operator-gated; this proxy injects the runtime operator token and never
// lets an arbitrary path through.
function isAllowed(method: "GET" | "POST", target: string): boolean {
  if (method === "GET") {
    if (target === "") return true;
    const parts = target.split("/");
    return parts.length === 1 && Boolean(parts[0]);
  }
  const parts = target.split("/");
  return parts.length === 2 && ["cancel", "steer"].includes(parts[1]);
}

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "POST",
): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported delegation route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/delegations${target ? `/${target}` : ""}`);
    new URL(request.url).searchParams.forEach((v, k) => url.searchParams.set(k, v));
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      method,
      headers: {
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        ...(await runtimeIdentityHeaders(request)),
        ...(method !== "GET" ? { "Content-Type": "application/json" } : {}),
      },
      body: method !== "GET" ? await request.text() : undefined,
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `runtime returned ${res.status}`, detail: body },
        { status: res.status === 400 || res.status === 403 || res.status === 404 ? res.status : 502 },
      );
    }
    return NextResponse.json(body as Record<string, unknown>);
  } catch (err) {
    console.error(`[api/delegations] ${method} ${target} failed:`, err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "delegation runtime unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "POST");
}
