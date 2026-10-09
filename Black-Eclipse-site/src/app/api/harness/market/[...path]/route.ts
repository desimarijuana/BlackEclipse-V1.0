import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { resolveProviderKey } from "@/lib/provider-keys";

export const dynamic = "force-dynamic";

// ── Market Data Layer admin proxy ────────────────────────────────────────────
// Reads pass straight through to the Python `/market/*` routes (which are the
// SAME state the agent tools use). For `/market/providers`, this route — the
// side that owns the encrypted vault — merges credential PRESENCE (never the
// value), exactly like the financial-gateway proxy. No secret crosses.
const ALLOWED_GET = new Set(["providers", "health", "quality", "stream"]);
const ALLOWED_POST = new Set(["stream/subscribe", "stream/unsubscribe"]);

async function proxy(request: Request, path: string[], method: "GET" | "POST"): Promise<Response> {
  const target = path.join("/");
  const allowed = method === "GET" ? ALLOWED_GET.has(target) : ALLOWED_POST.has(target);
  if (!allowed) {
    return NextResponse.json({ status: "UNAVAILABLE", error: `unsupported market route: ${method} ${target}` }, { status: 404 });
  }
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/market/${target}`);
    const incoming = new URL(request.url);
    incoming.searchParams.forEach((v, k) => url.searchParams.set(k, v));
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      method,
      headers: {
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        ...(await runtimeIdentityHeaders(request)),
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
      },
      body: method === "POST" ? await request.text() : undefined,
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json({ status: "UNAVAILABLE", error: `runtime returned ${res.status}` }, { status: 502 });
    }
    const payload = (await res.json()) as Record<string, unknown>;
    if (target === "providers" && Array.isArray(payload.providers)) {
      const rows = await Promise.all(
        (payload.providers as Array<Record<string, unknown>>).map(async (p) => {
          const ref = typeof p.credentialRef === "string" ? p.credentialRef : null;
          if (!ref) return p;
          const value = await resolveProviderKey(ref).catch(() => null);
          return { ...p, configured: Boolean(value && value.trim()) };
        }),
      );
      return NextResponse.json({ ...payload, providers: rows });
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error(`[api/harness/market] ${method} ${target} failed:`, err);
    return NextResponse.json({ status: "UNAVAILABLE", error: "market data layer unavailable" }, { status: 503 });
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return proxy(request, path, "POST");
}
