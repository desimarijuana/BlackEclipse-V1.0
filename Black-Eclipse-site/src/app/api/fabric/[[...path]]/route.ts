import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Execution Fabric proxy ───────────────────────────────────────────────────
// Passes through to the Python `/fabric/*` routes (the Execution Fabric admin
// API). The Python routes are operator-gated; this proxy injects the runtime
// operator token so no secret crosses the wire. Only the known console surface
// is reachable — an arbitrary path is refused.
const GET_EXACT = new Set(["", "status", "health", "queues", "metrics", "workers", "jobs", "dlq"]);
const POST_EXACT = new Set(["jobs"]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") {
    if (GET_EXACT.has(target)) return true;
    if (!target.startsWith("jobs/")) return false;
    const rest = target.slice("jobs/".length);
    if (!rest) return false;
    // jobs/{id} or jobs/{id}/{events|attempts|children}
    const parts = rest.split("/");
    return parts.length === 1 || (parts.length === 2 && ["events", "attempts", "children"].includes(parts[1]));
  }
  if (method === "POST") {
    if (POST_EXACT.has(target)) return true;
    return (
      (target.startsWith("jobs/") && (target.endsWith("/cancel") || target.endsWith("/retry"))) ||
      (target.startsWith("dlq/") && target.endsWith("/replay"))
    );
  }
  return false;
}

async function proxy(request: Request, path: string[], method: "GET" | "POST"): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported fabric route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/fabric${target ? `/${target}` : ""}`);
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
    console.error(`[api/fabric] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "execution fabric unavailable" }, { status: 503 });
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
