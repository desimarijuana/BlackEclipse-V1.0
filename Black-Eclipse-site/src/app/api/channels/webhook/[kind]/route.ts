import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";

export const dynamic = "force-dynamic";

// ── Public channel webhook receiver ──────────────────────────────────────────
// An external provider (Slack / WhatsApp / a generic webhook) posts here. This is
// deliberately NOT operator-gated: the caller is a third party. Authenticity is
// proven in the Python runtime by an HMAC over the RAW body under the channel's
// configured secret, so the body must be forwarded byte-for-byte — never parsed
// or re-serialized here. The middleware exempts this prefix from the session gate.
const FORWARD_HEADERS = [
  "x-slack-signature",
  "x-slack-request-timestamp",
  "x-hub-signature-256",
  "x-eclipse-signature",
  "content-type",
];

async function forward(request: Request, kind: string, method: "GET" | "POST"): Promise<Response> {
  try {
    await ensurePythonRuntime();
    const incoming = new URL(request.url);
    const url = new URL(`${HARNESS_PY_URL}/channels/webhook/${encodeURIComponent(kind)}`);
    incoming.searchParams.forEach((v, k) => url.searchParams.set(k, v));
    const headers: Record<string, string> = {};
    for (const name of FORWARD_HEADERS) {
      const value = request.headers.get(name);
      if (value) headers[name] = value;
    }
    const res = await fetch(url, {
      method,
      headers,
      body: method === "POST" ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    });
    const text = await res.text();
    const contentType = res.headers.get("content-type") || "application/json";
    return new NextResponse(text, { status: res.status, headers: { "Content-Type": contentType } });
  } catch (err) {
    console.error(`[api/channels/webhook] ${method} ${kind} failed:`, err);
    return NextResponse.json({ error: "channel gateway unavailable" }, { status: 503 });
  }
}

export async function GET(request: Request, ctx: { params: Promise<{ kind: string }> }) {
  const { kind } = await ctx.params;
  return forward(request, kind, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ kind: string }> }) {
  const { kind } = await ctx.params;
  return forward(request, kind, "POST");
}
