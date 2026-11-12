import { NextResponse } from "next/server";
import { listLearningReviewsPage } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning-review — bounded review audit list.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || undefined;
    const limit = url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : 50;
    const offset = url.searchParams.get("offset") ? Number(url.searchParams.get("offset")) : 0;
    const page = await listLearningReviewsPage(status, limit, offset);
    return NextResponse.json({ success: true, ...page });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning review list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
