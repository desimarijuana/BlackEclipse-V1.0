import { NextResponse } from "next/server";
import { getRuntimeHealth, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/health — provider health, latency percentiles,
// error rates and circuit state. Read-only; no credentials.
export async function GET() {
  try {
    const health = await getRuntimeHealth();
    return NextResponse.json({ success: true, ...health });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/health] GET error:", err);
    return NextResponse.json({ error: "Failed to load model health" }, { status });
  }
}
