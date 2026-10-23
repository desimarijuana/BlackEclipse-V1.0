import { NextResponse } from "next/server";
import { getEvolutionAutonomyStatus } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const result = await getEvolutionAutonomyStatus();
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "autonomy status failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
