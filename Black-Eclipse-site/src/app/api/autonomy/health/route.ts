import { NextResponse } from "next/server";
import { getAutonomyHealth } from "@/lib/harness/clients/autonomy-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

/** The goal/loop engine's mode + counters, for the chat status strip. */
export async function GET() {
  try {
    const health = await getAutonomyHealth();
    return NextResponse.json({ success: true, health });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "autonomy health failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
