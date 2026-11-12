import { NextResponse } from "next/server";
import { listMemoryEvents } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/events — memory + skill audit events.
export async function GET() {
  try {
    const result = await listMemoryEvents();
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "events failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
