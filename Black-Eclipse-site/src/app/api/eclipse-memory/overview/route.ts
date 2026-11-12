import { NextResponse } from "next/server";
import { memoryOverview } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/overview — real counts for the Memory Overview.
export async function GET() {
  try {
    const overview = await memoryOverview();
    return NextResponse.json({ success: true, ...overview });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory overview failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
