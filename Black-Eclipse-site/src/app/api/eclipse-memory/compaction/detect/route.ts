import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { detectCompaction } from "@/lib/harness/clients/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/compaction/detect — detect + persist inert proposals.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "memory-compaction-detect");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const proposals = await detectCompaction();
    return NextResponse.json({ success: true, proposals });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "compaction detect failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
