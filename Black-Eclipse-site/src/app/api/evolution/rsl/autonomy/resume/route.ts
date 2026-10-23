import { NextResponse } from "next/server";
import { resumeEvolutionAutonomy } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const result = await resumeEvolutionAutonomy();
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "resume autonomy failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
