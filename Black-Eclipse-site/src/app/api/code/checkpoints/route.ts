import { NextResponse } from "next/server";
import { listFileCheckpoints } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/code/checkpoints — the shadow-git snapshots for the selected project.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get("limit") ?? 50);
  try {
    return NextResponse.json({
      success: true,
      checkpoints: await listFileCheckpoints(Number.isFinite(limit) ? limit : 50),
    });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "checkpoint lookup failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
