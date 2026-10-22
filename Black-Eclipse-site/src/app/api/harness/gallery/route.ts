import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// GET/POST /api/harness/gallery - the local catalogue of published strategies.
//
// A thin front door onto the runtime's gallery: it forwards the call
// unchanged, attaches the operator token and turns a refusal into an honest
// error. It stores nothing itself.
async function forward(method: "GET" | "POST", path: string, body?: unknown) {
  try {
    await ensurePythonRuntime();
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(new URL(`${HARNESS_PY_URL}${path}`), {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: "no-store",
    });
    const payload = (await res.json().catch(() => ({}))) as {
      detail?: { message?: string } | string;
      error?: string;
    };
    if (!res.ok) {
      const detail = payload.detail;
      const message =
        typeof detail === "object" && detail && "message" in detail
          ? String(detail.message)
          : typeof detail === "string"
            ? detail
            : `the gallery returned ${res.status}`;
      return NextResponse.json({ error: message }, { status: res.status });
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/harness/gallery] request failed:", err);
    return NextResponse.json(
      { error: "the gallery is unavailable" },
      { status: 503 },
    );
  }
}

export async function GET() {
  return await forward("GET", "/gallery");
}

export async function POST(request: Request) {
  let body: unknown = undefined;
  try {
    body = await request.json();
  } catch {
    body = undefined;
  }
  return await forward("POST", "/gallery", body);
}
