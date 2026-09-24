import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { learnFromRun, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/learning/from-run/:runId — "Learn from this run". Creates learning
// candidate(s) from a run trace; NEVER enables a skill. Operator-gated.
export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const blocked = guardMutation(request, "learning-from-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { runId } = await params;
    const body = (await request.json().catch(() => ({}))) as { userIntent?: string };
    const result = await learnFromRun(runId, isOperatorRequest(request), body.userIntent);
    return NextResponse.json(result, { status: result.ok ? 200 : 403 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learning capture failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
