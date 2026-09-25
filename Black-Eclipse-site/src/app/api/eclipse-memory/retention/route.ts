import { NextResponse } from "next/server";
import { memoryRetention } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/retention — policy state + last sweep (no content).
export async function GET() {
  try {
    const body = await memoryRetention();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "retention status failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
