import { NextResponse } from "next/server";
import { getRunFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/runs/[id] — run status, read from the Python runtime store.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const run = await getRunFromRuntime(id);
    if (!run) return NextResponse.json({ error: "Run not found" }, { status: 404 });
    return NextResponse.json({ success: true, run });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/runs/[id]] GET error:", err);
    return NextResponse.json({ error: "Failed to load run" }, { status });
  }
}
