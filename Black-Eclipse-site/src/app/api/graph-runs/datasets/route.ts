// ── /api/graph-runs/datasets — saved local datasets ──────────────────────────
// Read-only metadata for the dataset picker. The payload itself stays in the
// runtime's local store; this never exposes a value, only ref/name/type/size.

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json(
      { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
      { status: 503 },
    );
  }
  const token = runtimeCallbackToken();
  const user = request.headers.get("x-eclipse-user");
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/datasets?limit=100`, {
      headers: {
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
        ...(user ? { "X-Harness-User": user } : {}),
      },
      signal: AbortSignal.timeout(15_000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to list datasets" },
      { status: 502 },
    );
  }
}
