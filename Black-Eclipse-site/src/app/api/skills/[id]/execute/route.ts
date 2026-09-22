import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { executeSkill, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { ExecutionMode } from "@/lib/harness/skills-types";

export const dynamic = "force-dynamic";
export const maxDuration = 240;

const MODES: ExecutionMode[] = ["interactive", "workflow", "scheduled", "agent", "evaluation"];

// POST /api/skills/:id/execute — the workflow-ready skill execution contract.
// The same endpoint serves every execution mode. Operator status is derived
// server-side from the runtime secret; a client cannot claim it by body alone.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardExpensiveMutation(request, "skill-execute", { limit: 20, windowMs: 5 * 60_000 });
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const mode = typeof body.executionMode === "string" && MODES.includes(body.executionMode as ExecutionMode)
      ? (body.executionMode as ExecutionMode)
      : "interactive";
    const result = await executeSkill(
      {
        skillId: id,
        version: typeof body.version === "string" ? body.version : undefined,
        input: body.input && typeof body.input === "object" ? (body.input as Record<string, unknown>) : {},
        runId: typeof body.runId === "string" ? body.runId : undefined,
        parentRunId: typeof body.parentRunId === "string" ? body.parentRunId : undefined,
        executionMode: mode,
        timeoutMs: typeof body.timeoutMs === "number" ? body.timeoutMs : undefined,
        metadata: body.metadata && typeof body.metadata === "object" ? (body.metadata as Record<string, unknown>) : undefined,
      },
      { operator: isOperatorRequest(request) }
    );
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill execution failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
