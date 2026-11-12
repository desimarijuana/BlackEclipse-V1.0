import { NextResponse } from "next/server";
import { rollbackPromotion } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ rollbackId: string }> }) {
  const { rollbackId } = await params;
  if (!rollbackId) {
    return NextResponse.json({ error: "rollbackId is required" }, { status: 400 });
  }
  try {
    // The client sends `runId` in the query (see `rollbackPromotion`); accept a
    // body too so both shapes work. Without it the runtime cannot resolve the
    // project or write the `land.rolled_back` marker.
    const runId =
      new URL(request.url).searchParams.get("runId") ??
      ((await request.json().catch(() => ({}))) as { runId?: string }).runId;
    const rollback = await rollbackPromotion(rollbackId, runId ?? undefined);
    return NextResponse.json({ success: true, rollback });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rollback failed" },
      { status: unavailable ? 503 : 409 },
    );
  }
}
