import { NextResponse } from "next/server";
import { getRuntimeDecisions, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/model-runtime/routing/decisions?limit=20 — recent routing
// decision traces (the routing debug view). Read-only.
export async function GET(request: Request) {
  try {
    const limitParam = new URL(request.url).searchParams.get("limit");
    const limit = Number.isFinite(Number(limitParam)) ? Math.max(1, Math.min(Number(limitParam), 100)) : 20;
    const decisions = await getRuntimeDecisions(limit);
    return NextResponse.json({ success: true, decisions });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/routing/decisions] GET error:", err);
    return NextResponse.json({ error: "Failed to load routing decisions" }, { status });
  }
}
