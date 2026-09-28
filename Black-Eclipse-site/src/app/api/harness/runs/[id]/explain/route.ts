import { NextResponse } from "next/server";
import { getRunExplanationFromRuntime, getRunFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/runs/[id]/explain — why memory/skills influenced the run.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const run = await getRunFromRuntime(id);
    if (!run) return NextResponse.json({ error: "Run not found" }, { status: 404 });
    const explanation = await getRunExplanationFromRuntime(id);
    return NextResponse.json({ success: true, ...(explanation ?? {}) });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    return NextResponse.json({ error: "Failed to load run explanation" }, { status });
  }
}
