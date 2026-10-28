import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// ── Money guardrail operator proxy ───────────────────────────────────────────
// Reads state, updates caps, and evaluates a hypothetical intent against the
// Python `/finance-guardrails/*` routes. Paths are allowlisted; every Python
// route is operator-gated and this proxy injects the runtime operator token, so
// no secret reaches the browser.

const ALLOWED_GET = new Set(["status", "intents"]);
const ALLOWED_PUT = new Set(["config"]);
const ALLOWED_POST = new Set(["evaluate"]);

function isAllowed(method: string, target: string): boolean {
  if (method === "GET") return ALLOWED_GET.has(target);
  if (method === "PUT") return ALLOWED_PUT.has(target);
  if (method === "POST") return ALLOWED_POST.has(target);
  return false;
}

async function proxy(
  request: Request,
  path: string[],
  method: "GET" | "PUT" | "POST",
): Promise<Response> {
  const target = path.join("/");
  if (!isAllowed(method, target)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: `unsupported money-guardrail route: ${method} ${target}` },
      { status: 404 },
    );
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/finance-guardrails/${target}`);
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
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `runtime returned ${res.status}`, ...payload },
        { status: res.status === 400 || res.status === 404 ? res.status : 502 },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error(`[api/finance-guardrails] ${method} ${target} failed:`, err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "money guardrails unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function PUT(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "finance-guardrails-config");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "PUT");
}

export async function POST(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const blocked = guardMutation(request, "finance-guardrails-evaluate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path = [] } = await ctx.params;
  return proxy(request, path, "POST");
}
