import { NextResponse } from "next/server";
import { sessionOpen } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/session-search/[runId] — bounded window of a run's indexed messages.
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    return NextResponse.json({ success: true, ...(await sessionOpen(runId)) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "session open failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
