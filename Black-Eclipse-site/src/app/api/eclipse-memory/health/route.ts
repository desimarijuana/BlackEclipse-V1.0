import { NextResponse } from "next/server";
import { memoryHealth } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/health — database liveness/migration status.
export async function GET() {
  try {
    return NextResponse.json({ success: true, ...(await memoryHealth()) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory health failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
