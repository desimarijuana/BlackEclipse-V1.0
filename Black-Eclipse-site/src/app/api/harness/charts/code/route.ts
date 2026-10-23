import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// POST /api/harness/charts/code — the editable starting script for a chart.
//
// The body is a chart SPEC (data only). The runtime validates it, resolves any
// named series exactly as the render route does, and returns a matplotlib
// program plus the names of any marks it could not reproduce. The script is a
// starting point; the declarative chart remains the canonical output.
export async function POST(request: Request) {
  let spec: unknown;
  try {
    spec = await request.json();
  } catch {
    return NextResponse.json(
      { status: "INVALID", error: "the chart request was not readable" },
      { status: 400 },
    );
  }
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) {
    return NextResponse.json(
      { status: "INVALID", error: "a chart request must be a chart spec" },
      { status: 400 },
    );
  }

  try {
    await ensurePythonRuntime();
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/charts/code`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      body: JSON.stringify(spec),
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
    const payload = (await res.json().catch(() => ({}))) as {
      source?: string;
      unsupported?: string[];
      detail?: { code?: string; message?: string } | string;
    };
    if (!res.ok) {
      const detail = payload.detail;
      const message =
        typeof detail === "object" && detail && "message" in detail
          ? String(detail.message)
          : typeof detail === "string"
            ? detail
            : `the chart engine returned ${res.status}`;
      return NextResponse.json(
        { status: "UNAVAILABLE", error: message, detail },
        { status: res.status },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/harness/charts/code] POST error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the chart engine is unavailable" },
      { status: 503 },
    );
  }
}
