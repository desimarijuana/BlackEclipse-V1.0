import { NextResponse } from "next/server";
import { learningReviewHealth } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning-review/health — queue + audit health.
export async function GET() {
  try {
    return NextResponse.json({ success: true, ...(await learningReviewHealth()) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning review health failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
