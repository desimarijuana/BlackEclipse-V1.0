// ── /api/graph-runs/health — bounded graph-run telemetry ────────────────────

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }
  const url = new URL(request.url);
  const windowHours = url.searchParams.get("windowHours") ?? "24";
  const token = runtimeCallbackToken();
  try {
    const res = await fetch(
      `${HARNESS_PY_URL}/graphs/health?windowHours=${encodeURIComponent(windowHours)}`,
      {
        headers: {
          ...(token ? { "X-Harness-Operator": token } : {}),
          ...(await runtimeIdentityHeaders(request)),
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to load graph health" },
      { status: 502 },
    );
  }
}
