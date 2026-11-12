import { NextResponse } from "next/server";
import { getLearningEligibility } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning/eligibility/:runId — read-only eligibility reason for a run.
// Tells the chat surface why a run is (or is not) a learning candidate and links
// to the Learning Queue. Creates nothing.
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    return NextResponse.json(await getLearningEligibility(runId));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "eligibility lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
