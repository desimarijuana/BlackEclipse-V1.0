import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// ── Unified Search admin proxy ───────────────────────────────────────────────
// Reads and writes pass straight through to the Python `/search/*` routes (the
// SAME SearchService the agent tools use). The Python routes are operator-gated;
// this proxy injects the runtime operator token, so no secret crosses the wire.
const ALLOWED_GET = new Set(["health", "stats", "models", "documents", "events"]);
const ALLOWED_POST = new Set(["", "debug", "index", "index/process", "ingest", "find-similar"]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") {
    return ALLOWED_GET.has(target) || target.startsWith("documents/");
  }
  if (method === "POST") {
    return (
      ALLOWED_POST.has(target) ||
      target.startsWith("reindex/") ||
      target.startsWith("debug")
    );
  }
  if (method === "DELETE") {
    return target.startsWith("documents/");
  }
  return false;
}

async function proxy(request: Request, path: string[], method: "GET" | "POST" | "DELETE"): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json({ status: "UNAVAILABLE", error: `unsupported search route: ${method} ${target}` }, { status: 404 });
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/search${target ? `/${target}` : ""}`);
    const incoming = new URL(request.url);
    incoming.searchParams.forEach((v, k) => url.searchParams.set(k, v));
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      method,
      headers: {
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        ...(method !== "GET" ? { "Content-Type": "application/json" } : {}),
      },
      body: method !== "GET" ? await request.text() : undefined,
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json({ status: "UNAVAILABLE", error: `runtime returned ${res.status}` }, { status: 502 });
    }
    return NextResponse.json((await res.json()) as Record<string, unknown>);
  } catch (err) {
    console.error(`[api/harness/search] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "search layer unavailable" }, { status: 503 });
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
