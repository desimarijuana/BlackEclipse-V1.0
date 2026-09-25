import { NextResponse } from "next/server";
import { exportMemory } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/export — readable, versioned JSON of the memory domain.
export async function GET() {
  try {
    const body = await exportMemory();
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "export failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
