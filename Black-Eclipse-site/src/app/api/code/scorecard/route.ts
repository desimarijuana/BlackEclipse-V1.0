import { NextResponse } from "next/server";
import { getCodeScorecard } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const days = Number(new URL(request.url).searchParams.get("days") ?? 30);
  try {
    const scorecard = await getCodeScorecard(Number.isFinite(days) ? days : 30);
    return NextResponse.json({ success: true, scorecard });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not load the scorecard" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
