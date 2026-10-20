import { NextResponse } from "next/server";
import { getEvolutionRslStatus } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await getEvolutionRslStatus();
    return NextResponse.json({ success: true, ...status });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "RSL status failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
