import { NextResponse } from "next/server";
import { memoryConflictReview } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/memories/:id/conflict — side-by-side competing memory
// view + safe resolution actions. Read-only.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const review = await memoryConflictReview(id);
    if (!review) return NextResponse.json({ error: "memory not found" }, { status: 404 });
    return NextResponse.json({ success: true, review });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "conflict review failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
