import { NextResponse } from "next/server";
import { memoryPreferences } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/preferences — the Personal Memory → Preferences read
// model: active learned preferences, pending inferences, evidence groups,
// dimensions and the thresholds in force. Read-only.
export async function GET(request: Request) {
  try {
    const scopeId = new URL(request.url).searchParams.get("scopeId") || undefined;
    const result = await memoryPreferences(scopeId);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "preference summary failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
