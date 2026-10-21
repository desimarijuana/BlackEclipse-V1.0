import { NextResponse } from "next/server";
import { setEvolutionClimbPaused } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    return NextResponse.json(await setEvolutionClimbPaused(true));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "pause failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
