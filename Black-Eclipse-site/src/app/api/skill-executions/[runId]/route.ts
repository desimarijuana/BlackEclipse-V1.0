import { NextResponse } from "next/server";
import { getSkillExecution, cancelSkillExecution } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// GET /api/skill-executions/:runId — one skill execution (the trace view).
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const execution = await getSkillExecution(runId);
    if (!execution) return NextResponse.json({ error: "Skill execution not found" }, { status: 404 });
    return NextResponse.json({ success: true, execution });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "execution lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// DELETE /api/skill-executions/:runId — cancel a running skill execution.
export async function DELETE(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  // Cancelling a run is a mutation (operator-gated).
  const blocked = guardMutation(request, "skill-execution-cancel");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { runId } = await params;
    const cancelled = await cancelSkillExecution(runId);
    return NextResponse.json({ success: true, cancelled });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "cancel failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
