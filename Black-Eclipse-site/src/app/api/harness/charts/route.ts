import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// POST /api/harness/charts — draw a chart with the runtime's chart engine.
//
// The body is a chart SPEC: data only (a kind, some series, a title). The
// runtime validates it, draws it with matplotlib and records the PNG in the
// Artifact Center; this route returns the figure metadata and the artifact id,
// and the browser fetches the picture back through /api/artifacts.
//
// The route is the front door's validation boundary: it forwards the spec
// unchanged (the runtime owns the spec contract) and turns a runtime refusal
// into an honest error the UI can show. It never draws anything itself.
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
    const ready = await ensurePythonRuntime();
    if (!ready) {
      return NextResponse.json(
        {
          status: "UNAVAILABLE",
          error:
            "the chart engine is unavailable — install the Python runtime with `npm run setup:python`",
        },
        { status: 503 },
      );
    }
    const url = new URL(`${HARNESS_PY_URL}/charts/render`);
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      body: JSON.stringify(spec),
      cache: "no-store",
    });
    const payload = (await res.json().catch(() => ({}))) as {
      status?: string;
      figure?: unknown;
      artifact?: unknown;
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
    console.error("[api/harness/charts] POST error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the chart engine is unavailable" },
      { status: 503 },
    );
  }
}
