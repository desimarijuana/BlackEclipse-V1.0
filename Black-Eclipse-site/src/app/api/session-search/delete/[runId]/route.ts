import { NextResponse } from "next/server";
import { sessionDelete } from "@/lib/harness/clients/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/session-search/delete/[runId] — operator: remove a run's indexed
// messages (the full agent-memory run trace is untouched).
export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const blocked = guardMutation(request, "session-search-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const { runId } = await params;
    return NextResponse.json(await sessionDelete(runId, true));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "session delete failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
