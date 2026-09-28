import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { resolveMemoryConflict } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/memories/:id/resolve — apply a conflict-resolution
// action (keep/supersede/merge/confirm_both/dismiss/defer). Operator-gated;
// every action is reversible/audited.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "memory-conflict-resolve");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as {
      action?: string; targetId?: string; mergedContent?: string; reason?: string;
    };
    if (!body.action) return NextResponse.json({ error: "action is required" }, { status: 400 });
    const result = await resolveMemoryConflict(id, body.action, {
      targetId: body.targetId, mergedContent: body.mergedContent, reason: body.reason,
    });
    return NextResponse.json(result, { status: result.ok ? 200 : 400 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "resolution failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
