import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  getRunFromRuntime,
  HarnessRuntimeUnavailable,
  resumeRunInRuntime,
} from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/runs/[id]/resume — resume a run left `interrupted` by a
// runtime restart, from its latest checkpoint. The caller must supply the
// original RunRequest-shaped payload (input + agent + model settings): the
// stored run row does not contain the full model configuration, so the runtime
// cannot reconstruct it safely on its own.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "harness-resume");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const { id } = await params;
  try {
    const run = await getRunFromRuntime(id);
    if (!run) return NextResponse.json({ error: "Run not found" }, { status: 404 });

    const status = String((run as { status?: unknown }).status ?? "");
    if (status === "completed" || status === "failed" || status === "cancelled") {
      return NextResponse.json(
        { error: `Run is already terminal (${status}) and cannot be resumed`, code: "RESUME_CONFLICT" },
        { status: 409 }
      );
    }

    const body = await request.json().catch(() => null);
    if (!body || typeof body !== "object" || !(body as { input?: unknown }).input) {
      return NextResponse.json(
        {
          error:
            "The original run request is required to resume (input + agent + model settings); the stored row does not carry the full model configuration",
          code: "RESUME_REQUEST_REQUIRED",
        },
        { status: 400 }
      );
    }

    const result = await resumeRunInRuntime(id, body as Record<string, unknown>);
    return NextResponse.json({ success: true, runId: id, status: "running", ...result }, { status: 202 });
  } catch (err) {
    const code = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/runs/[id]/resume] POST error:", err);
    return NextResponse.json({ error: "Failed to resume run" }, { status: code });
  }
}
