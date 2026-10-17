import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Channel Gateway proxy ─────────────────────────────────────────────────────
// Passes through to the Python `/channels/*` routes (Settings › Connections). The
// Python routes are operator-gated; this proxy injects the runtime operator token
// so no secret crosses the wire. Only the known surface is reachable — an
// arbitrary path is refused. Config values are redacted by Python (presence
// flags only), so a credential never reaches this proxy's response.
const GET_EXACT = new Set(["", "health", "bindings", "messages"]);
const POST_EXACT = new Set(["link-code", "inbound", "send"]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") return GET_EXACT.has(target);
  if (method === "POST") {
    if (POST_EXACT.has(target)) return true;
    return target.startsWith("bindings/") && target.endsWith("/scope");
  }
  if (method === "PUT") {
    // /channels/{kind}
    return target.length > 0 && !target.includes("/");
  }
  if (method === "DELETE") {
    if (!target) return false;
    if (target.startsWith("bindings/")) return target.split("/").length === 2;
    return !target.includes("/");
  }
  return false;
}

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "POST" | "PUT" | "DELETE",
): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported channel route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/channels${target ? `/${target}` : ""}`);
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
    console.error(`[api/channels] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "channel gateway unavailable" }, { status: 503 });
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

export async function PUT(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "PUT");
}

export async function DELETE(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "DELETE");
}
