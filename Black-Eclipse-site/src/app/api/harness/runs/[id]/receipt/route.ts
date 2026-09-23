import { NextResponse } from "next/server";
import { getRunReceiptFromRuntime, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/runs/[id]/receipt — the run's durable research receipt.
// Read-only; 404 when the run has no receipt (ordinary chat / older run).
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const receipt = await getRunReceiptFromRuntime(id);
    if (!receipt) return NextResponse.json({ error: "Receipt not found" }, { status: 404 });
    return NextResponse.json({ success: true, receipt });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/runs/[id]/receipt] GET error:", err);
    return NextResponse.json({ error: "Failed to load receipt" }, { status });
  }
}
