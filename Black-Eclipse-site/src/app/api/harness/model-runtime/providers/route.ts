import { NextResponse } from "next/server";
import { listRuntimeProviders, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/providers — the registered model providers and
// their routing/health availability. Read-only; never returns credentials.
export async function GET() {
  try {
    const providers = await listRuntimeProviders();
    return NextResponse.json({ success: true, providers });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/providers] GET error:", err);
    return NextResponse.json({ error: "Failed to load model providers" }, { status });
  }
}
