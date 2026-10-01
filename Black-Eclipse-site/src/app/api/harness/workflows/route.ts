import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listWorkflows, saveWorkflow } from "@/lib/harness/workflows-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/workflows — list saved workflow definitions.
export async function GET() {
  try {
    const workflows = await listWorkflows();
    return NextResponse.json({ workflows });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to list workflows" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

// POST /api/harness/workflows — create/update a workflow. Python validates the
// definition before storage; a rejection returns 400 with the NAMED reason.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "workflows-save");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const result = await saveWorkflow(body as never);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to save workflow" },
      { status: unavailable ? 503 : 400 },
    );
  }
}
