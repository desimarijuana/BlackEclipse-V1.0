import { NextResponse } from "next/server";
import { getRuntimeUsage, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/usage — normalized usage, cost and persisted
// per-request/health rows from the model runtime's own store. Cost that was
// unknown is reported as such (never 0).
export async function GET() {
  try {
    const usage = await getRuntimeUsage();
    return NextResponse.json({ success: true, ...usage });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/usage] GET error:", err);
    return NextResponse.json({ error: "Failed to load model usage" }, { status });
  }
}
