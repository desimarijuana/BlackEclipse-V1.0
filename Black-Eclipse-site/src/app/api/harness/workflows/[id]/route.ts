import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getWorkflow, deleteWorkflow } from "@/lib/harness/workflows-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/workflows/:id — one workflow definition (by version).
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const version = new URL(request.url).searchParams.get("version") ?? undefined;
    const workflow = await getWorkflow(id, version);
    if (!workflow) return NextResponse.json({ error: "workflow not found" }, { status: 404 });
    return NextResponse.json({ workflow });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to load workflow" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

// DELETE /api/harness/workflows/:id — remove a workflow (operator-gated).
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "workflows-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const version = new URL(request.url).searchParams.get("version") ?? undefined;
    const deleted = await deleteWorkflow(id, version);
    return NextResponse.json({ success: true, deleted });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to delete workflow" },
      { status: unavailable ? 503 : 400 },
    );
  }
}
