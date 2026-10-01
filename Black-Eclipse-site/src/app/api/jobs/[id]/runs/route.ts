import { NextResponse } from "next/server";
import { listJobRuns } from "@/lib/harness/jobs-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const runs = await listJobRuns(id);
    return NextResponse.json({ success: true, runs });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "run list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
