import { NextResponse } from "next/server";
import { listCandidates } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/learning/candidates — the Learning Queue.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || undefined;
    const candidates = await listCandidates(status);
    return NextResponse.json({ success: true, candidates });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "candidate list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
