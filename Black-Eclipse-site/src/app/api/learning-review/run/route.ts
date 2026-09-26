import { NextResponse } from "next/server";
import { runLearningReview } from "@/lib/harness/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/learning-review/run — operator: run a review for one run.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "learning-review-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { runId?: string; model?: boolean };
    if (!body.runId) return NextResponse.json({ error: "runId is required" }, { status: 400 });
    return NextResponse.json(await runLearningReview(true, body.runId, Boolean(body.model)));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning review failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
