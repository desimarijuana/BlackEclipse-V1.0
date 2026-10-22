import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// /api/harness/projects/* -> the runtime's /projects/* routes.
//
// The project surface is more than a list: the curated view, the proposals and
// the run that closes the loop all live behind the same entity. This proxy is
// the front door onto them - it forwards the call unchanged, attaches the
// operator token, and turns a runtime refusal into an honest error. It stores
// nothing itself.

async function forward(request: Request, method: "GET" | "POST" | "DELETE",
                        path: string[], body?: unknown) {
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/projects/${path.map(encodeURIComponent).join("/")}`);
    const search = new URL(request.url).search;
    if (search) url.search = search;
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

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, ctx: Ctx) {
  try {
    const { path } = await ctx.params;
    return await forward(request, "GET", path);
  } catch (err) {
    console.error("[api/harness/projects] GET error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the project layer is unavailable" },
      { status: 503 },
    );
  }
}

export async function POST(request: Request, ctx: Ctx) {
  try {
    const { path } = await ctx.params;
    let body: unknown = undefined;
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
    return await forward(request, "POST", path, body);
  } catch (err) {
    console.error("[api/harness/projects] POST error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the project layer is unavailable" },
      { status: 503 },
    );
  }
}

export async function DELETE(request: Request, ctx: Ctx) {
  try {
    const { path } = await ctx.params;
    return await forward(request, "DELETE", path);
  } catch (err) {
    console.error("[api/harness/projects] DELETE error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the project layer is unavailable" },
      { status: 503 },
    );
  }
}
