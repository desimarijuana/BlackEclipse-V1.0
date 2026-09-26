import { NextResponse } from "next/server";
import { sessionSearchHealth } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/session-search/health — index health + FTS5 availability.
export async function GET() {
  try {
    return NextResponse.json({ success: true, ...(await sessionSearchHealth()) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "session search health failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
