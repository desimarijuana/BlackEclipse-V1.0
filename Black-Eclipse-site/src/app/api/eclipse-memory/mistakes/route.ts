import { NextResponse } from "next/server";
import { listMistakes } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/mistakes — captured mistakes/recoveries.
export async function GET() {
  try {
    return NextResponse.json({ success: true, mistakes: await listMistakes() });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "mistakes failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
