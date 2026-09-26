import { NextResponse } from "next/server";
import { decideLearningReview } from "@/lib/harness/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/learning-review/decide — operator: accept/reject one review outcome.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "learning-review-decide");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as {
      reviewId?: string;
      outcomeIndex?: number;
      action?: "accept" | "reject";
    };
    if (!body.reviewId || !body.action) {
      return NextResponse.json({ error: "reviewId and action are required" }, { status: 400 });
    }
    return NextResponse.json(
      await decideLearningReview(true, body.reviewId, body.outcomeIndex ?? 0, body.action)
    );
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning review decision failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}
