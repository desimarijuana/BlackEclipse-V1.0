import { NextResponse } from "next/server";
import { getCodeScorecard } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const days = Number(url.searchParams.get("days") ?? 30);
  const taskId = url.searchParams.get("taskId") ?? undefined;
  const rootId = url.searchParams.get("rootId") ?? undefined;
  try {
    const scorecard = await getCodeScorecard(Number.isFinite(days) ? days : 30, {
      ...(taskId ? { taskId } : {}),
      ...(rootId ? { rootId } : {}),
    });
    return NextResponse.json({ success: true, scorecard });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not load the scorecard" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
