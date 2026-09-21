import { NextResponse } from "next/server";
import { getEventsFromRuntime, getRunFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/runs/[id]/events — the persisted, ordered trace from the
// Python runtime.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const run = await getRunFromRuntime(id);
    if (!run) return NextResponse.json({ error: "Run not found" }, { status: 404 });
    const { events, toolExecutions } = await getEventsFromRuntime(id);
    return NextResponse.json({ success: true, runId: id, events, toolExecutions });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/runs/[id]/events] GET error:", err);
    return NextResponse.json({ error: "Failed to load events" }, { status });
  }
}
