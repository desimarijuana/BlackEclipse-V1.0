import { NextResponse } from "next/server";
import { listSkillEvaluations } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/:id/evaluations — evaluation history for a skill.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const evaluations = await listSkillEvaluations(id);
    return NextResponse.json({ success: true, evaluations });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "evaluation history failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
