import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { analyzeRun } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/analyze/:runId — deterministic post-run analysis
// (mistakes + policy-gated candidates). Never enables a skill.
export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const blocked = guardMutation(request, "eclipse-memory-analyze");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { runId } = await params;
    const result = await analyzeRun(runId);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "analysis failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
