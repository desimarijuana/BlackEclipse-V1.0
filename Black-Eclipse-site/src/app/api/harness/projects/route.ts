import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// GET/POST /api/harness/projects — the named scopes the agent and the UI share.
//
// A project holds the strategies, backtests, datasets and artifacts that belong
// to one piece of work. The runtime owns the store; this route is a thin
// front door onto it: it forwards the call unchanged, attaches the operator
// token, and turns a runtime refusal into an honest error the UI can show. It
// stores nothing itself.

async function forward(request: Request, method: "GET" | "POST", path: string, body?: unknown) {
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}${path}`);
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: "no-store",
    });
    const payload = (await res.json().catch(() => ({}))) as {
      detail?: { code?: string; message?: string } | string;
      error?: string;
    };
    if (!res.ok) {
      const detail = payload.detail;
      const message =
        typeof detail === "object" && detail && "message" in detail
          ? String(detail.message)
          : typeof detail === "string"
            ? detail
            : `the project layer returned ${res.status}`;
      return NextResponse.json(
        { status: "UNAVAILABLE", error: message, detail },
        { status: res.status },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/harness/projects] request failed:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the project layer is unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const query = url.searchParams.get("status");
  const limit = url.searchParams.get("limit");
  const params = new URLSearchParams();
  if (query) params.set("status", query);
  if (limit) params.set("limit", limit);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return await forward(request, "GET", `/projects${suffix}`);
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { status: "INVALID", error: "the project request was not readable" },
      { status: 400 },
    );
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json(
      { status: "INVALID", error: "a project request must be an object" },
      { status: 400 },
    );
  }
  return await forward(request, "POST", "/projects", body);
}
