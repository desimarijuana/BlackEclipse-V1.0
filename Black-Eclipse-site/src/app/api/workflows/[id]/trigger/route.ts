// ── /api/workflows/[id]/trigger — webhook-style trigger ──────────────────────
// Starts the workflow's CURRENT persisted version. Deliberately runs inside the
// TEST-RUN envelope: a trigger that can be called without a secret must not be
// able to perform write/network/trading effects. Secret-bearing webhook triggers
// (signature verification, per-workflow tokens) are Phase 8/10 work and are NOT
// implied by this route.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { startPersistedRun } from "@/lib/graph-studio/run-server";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "workflow-trigger");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;
  const result = await startPersistedRun({ workflowId: id, request, testRun: true });
  if (!result.ok) {
    return NextResponse.json(
      result.detail ? { error: result.error, detail: result.detail } : { error: result.error },
      { status: result.status },
    );
  }
  return NextResponse.json({ run: result.run }, { status: result.status });
}
