import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// GET /api/market/history - the local data vault: what history this machine
// already holds. The runtime owns the store; this route is a thin front door
// onto it, so the widget and the agent can never disagree about the data.
export async function GET() {
  try {
    await ensurePythonRuntime();
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(new URL(`${HARNESS_PY_URL}/market/history`), {
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
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
            : `the history catalog returned ${res.status}`;
      return NextResponse.json({ error: message }, { status: res.status });
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/market/history] GET error:", err);
    return NextResponse.json(
      { error: "the history catalog is unavailable" },
      { status: 503 },
    );
  }
}
