import { NextResponse } from "next/server";
import { getUsageSummaryFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/usage?days=30 — token-consumption analytics, read from the
// Python runtime's agent-memory database. Real persisted usage only; runs whose
// provider omitted a usage block contribute 0 tokens and are counted separately
// in `totals.runsWithUsage` (never fabricated).
export async function GET(request: Request) {
  try {
    const daysParam = new URL(request.url).searchParams.get("days");
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Math.min(Number(daysParam), 365)) : 30;
    const summary = await getUsageSummaryFromRuntime(days);
    return NextResponse.json({ success: true, ...summary });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/usage] GET error:", err);
    return NextResponse.json(
      { error: status === 503 ? "Agent runtime unavailable" : "Failed to load usage analytics" },
      { status }
    );
  }
}
