import { NextResponse } from "next/server";
import { getEvaluation } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/evaluations/:id — one evaluation with its test cases.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const evaluation = await getEvaluation(id);
    if (!evaluation) return NextResponse.json({ error: "Evaluation not found" }, { status: 404 });
    return NextResponse.json({ success: true, evaluation });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "evaluation lookup failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
