import { NextResponse } from "next/server";
import { listLearningReviews } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning-review — bounded review audit list.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || undefined;
    const limit = url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : 50;
    const reviews = await listLearningReviews(status, limit);
    return NextResponse.json({ success: true, reviews });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning review list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
