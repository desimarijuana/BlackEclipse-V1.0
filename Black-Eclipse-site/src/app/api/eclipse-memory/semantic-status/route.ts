import { NextResponse } from "next/server";
import { memorySemanticStatus } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/semantic-status — active conflict mode + fallback state.
export async function GET() {
  try {
    const body = await memorySemanticStatus();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "semantic status failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
