import { NextResponse } from "next/server";
import {
  HARNESS_PY_URL,
  ensurePythonRuntime,
  probeChartEngine,
} from "@/lib/harness/python-runtime";
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
//
// TWO different unavailabilities, two different messages:
//   * the runtime cannot boot at all (no interpreter / broken stack) — the
//     operator must repair the runtime;
//   * the runtime is healthy but the drawing library is missing — the runtime
//     is installed, `matplotlib`/`plotly` are not. Saying "install the runtime"
//     here sends the operator to fix something that already works.
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
            "the Python runtime is unavailable — it is installed but not running (or its agent stack is incomplete). Run `npm run setup:python`, then restart the app.",
          detail: {
            code: "RUNTIME_UNAVAILABLE",
            message:
              "the Python runtime is not available, so the chart engine cannot start. Run `npm run setup:python`.",
          },
        },
        { status: 503 },
      );
    }

    // The runtime is up. It still cannot draw without its plotting libraries,
    // and that is a DIFFERENT failure with a different repair.
    const engine = await probeChartEngine();
    if (!engine.ready) {
      const missing = engine.missing.length > 0 ? engine.missing.join(", ") : "matplotlib/plotly";
      const python = engine.python ?? "the selected Python interpreter";
      return NextResponse.json(
        {
          status: "UNAVAILABLE",
          error: `the chart engine cannot draw — ${python} is missing ${missing}. Run \`npm run setup:python\`.`,
          detail: {
            code: "CHART_RENDER_UNAVAILABLE",
            message: `the Python runtime at ${python} is missing ${missing}, so a chart cannot be drawn. Run \`npm run setup:python\`.`,
            missing: engine.missing,
            python: engine.python,
          },
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
      {
        status: "UNAVAILABLE",
        error: "the chart engine is unavailable — the runtime did not answer.",
        detail: {
          code: "RUNTIME_UNAVAILABLE",
          message: "the chart engine is unavailable — the runtime did not answer.",
        },
      },
      { status: 503 },
    );
  }
}
