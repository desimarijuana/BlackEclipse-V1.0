import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Security subsystem admin proxy ───────────────────────────────────────────
// Reads and administrator actions pass through to the Python `/security/*`
// routes (the SAME SecurityGateway the effect authorizers use). Every Python
// route is operator-gated; this proxy injects the runtime operator token, so no
// secret crosses the wire to the browser. Paths are allowlisted, never proxied
// blindly.
const ALLOWED_GET = new Set([
  "status",
  "health",
  "metrics",
  "policy",
  "audit",
  "audit/verify",
  "capabilities",
  "approvals",
]);
const ALLOWED_POST = new Set([
  "policy/reload",
  "capabilities",
  "check",
  "network/check",
]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") return ALLOWED_GET.has(target);
  if (method === "POST") {
    return ALLOWED_POST.has(target) || target.startsWith("capabilities/") || target.startsWith("approvals/");
  }
  return false;
}

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "POST",
): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported security route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/security${target ? `/${target}` : ""}`);
    const incoming = new URL(request.url);
    incoming.searchParams.forEach((v, k) => url.searchParams.set(k, v));
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
    if (!res.ok) {
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `runtime returned ${res.status}` },
        { status: res.status === 400 || res.status === 404 ? res.status : 502 },
      );
    }
    return NextResponse.json((await res.json()) as Record<string, unknown>);
  } catch (err) {
    console.error(`[api/security] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "security layer unavailable" }, { status: 503 });
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
