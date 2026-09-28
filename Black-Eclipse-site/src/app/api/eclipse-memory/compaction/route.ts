import { NextResponse } from "next/server";
import { listCompaction } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/compaction — inert near-duplicate proposals (read-only).
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const proposals = await listCompaction(url.searchParams.get("status") || undefined);
    return NextResponse.json({ success: true, proposals });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "compaction list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
