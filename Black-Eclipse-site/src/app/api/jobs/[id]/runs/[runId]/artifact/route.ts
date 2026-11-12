import { NextResponse } from "next/server";
import { getJobRunArtifact } from "@/lib/harness/clients/jobs-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// The saved report artifact for one run. The runtime DERIVES the path from the
// run id and refuses a read from a different scope — this route only forwards.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; runId: string }> },
) {
  const { id, runId } = await params;
  const scopeId = new URL(request.url).searchParams.get("scopeId") ?? undefined;
  try {
    const artifact = await getJobRunArtifact(id, runId, scopeId);
    return NextResponse.json({ success: true, artifact });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "artifact read failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
