import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Event Console proxy ──────────────────────────────────────────────────────
// Passes through to the Python `/events/*` routes (the Event System's console
// API). The Python routes are operator-gated; this proxy injects the runtime
// operator token so no secret crosses the wire. Only the known console surface
// is reachable — an arbitrary path is refused.
const GET_EXACT = new Set([
  "",
  "health",
  "metrics",
  "registry",
  "types",
  "subscriptions",
  "dlq",
  "graph",
  "rules",
]);
const POST_EXACT = new Set(["subscriptions", "replay", "rules"]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") {
    if (GET_EXACT.has(target)) return true;
    // dynamic detail routes: /dlq/{id} and /{eventId}
    return target.startsWith("dlq/") || (!target.includes("/") && target.length > 0);
  }
  if (method === "POST") {
    if (POST_EXACT.has(target)) return true;
    return target.startsWith("dlq/") && (target.endsWith("/retry") || target.endsWith("/discard"));
  }
  if (method === "DELETE") {
    return target.startsWith("subscriptions/");
  }
  return false;
}

async function proxy(request: Request, path: string[], method: "GET" | "POST" | "DELETE"): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json({ status: "UNAVAILABLE", error: `unsupported event route: ${method} ${target}` }, { status: 404 });
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/events${target ? `/${target}` : ""}`);
    const incoming = new URL(request.url);
    incoming.searchParams.forEach((v, k) => url.searchParams.set(k, v));
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
    console.error(`[api/events] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "event system unavailable" }, { status: 503 });
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

export async function DELETE(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "DELETE");
}
