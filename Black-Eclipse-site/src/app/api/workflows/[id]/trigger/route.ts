// ── /api/workflows/[id]/trigger — webhook-style trigger ──────────────────────
// Starts the workflow's CURRENT persisted version. The request body becomes the
// trigger's one-off `runInput` (JSON as-is; any other non-empty body is wrapped
// as `{ text }`), bounded by `validateRunInput`. Deliberately runs inside the
// TEST-RUN envelope: a trigger that can be called without a secret must not be
// able to perform write/network/trading effects. Secret-bearing webhook triggers
// (signature verification, per-workflow tokens) are Phase 8/10 work and are NOT
// implied by this route.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { startPersistedRun } from "@/lib/graph-studio/run-server";
import { validateRunInput } from "@/lib/graph-studio/run-input";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "workflow-trigger");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await ctx.params;

  // The request body becomes the trigger's Start value. JSON is used as-is;
  // any other non-empty body is wrapped as { text }. Bounded, never persisted.
  const raw = await request.text().catch(() => "");
  let runInput: unknown;
  if (raw.trim()) {
    try {
      runInput = JSON.parse(raw);
    } catch {
      runInput = { text: raw };
    }
  }
  const input = validateRunInput(runInput);
  if (!input.ok) {
    return NextResponse.json({ error: input.error }, { status: 400 });
  }

  const result = await startPersistedRun({
    workflowId: id,
    request,
    runInput: input.value,
    testRun: true,
  });
  if (!result.ok) {
    return NextResponse.json(
      result.detail ? { error: result.error, detail: result.detail } : { error: result.error },
      { status: result.status },
    );
  }
  return NextResponse.json({ run: result.run }, { status: result.status });
}
