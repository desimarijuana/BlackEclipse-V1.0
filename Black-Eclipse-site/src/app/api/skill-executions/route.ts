import { NextResponse } from "next/server";
import { listSkillExecutions } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skill-executions — list recent skill executions (optionally one skill).
// The `[runId]` route handles a single execution; this list route was missing,
// which made the Execution Activity tab fetch a 404 and render nothing.
export async function GET(request: Request) {
  try {
    const skillId = new URL(request.url).searchParams.get("skillId") ?? undefined;
    const executions = await listSkillExecutions(skillId);
    return NextResponse.json({ success: true, executions });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "execution list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
