import { NextResponse } from "next/server";
import { memoryDatabaseHealth } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/database-health — integrity + foreign-key + bloat check.
export async function GET() {
  try {
    const body = await memoryDatabaseHealth();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "database health failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
