import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { cancelRunInRuntime, getRunFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/runs/[id]/cancel — request cooperative cancellation in the
// Python runtime.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "harness-cancel");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const { id } = await params;
  try {
    const run = await getRunFromRuntime(id);
    if (!run) return NextResponse.json({ error: "Run not found" }, { status: 404 });
    const cancelled = await cancelRunInRuntime(id);
    return NextResponse.json({
      success: true,
      runId: id,
      cancelled,
      message: cancelled
        ? "Cancellation requested"
        : "Run is not active (already finished or not in this process)",
    });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/runs/[id]/cancel] POST error:", err);
    return NextResponse.json({ error: "Failed to cancel run" }, { status });
  }
}
