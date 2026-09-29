import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { labelConflict } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/memories/:id/conflict-label — operator ground-truth
// judgement (true_conflict | false_positive). Append-only; feeds the real-usage
// report's precision/recall.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "memory-conflict-label");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const label = body.label === "false_positive" ? "false_positive" : "true_conflict";
    const data = await labelConflict(
      id, label, true,
      typeof body.reason === "string" ? body.reason : undefined
    );
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "label failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
