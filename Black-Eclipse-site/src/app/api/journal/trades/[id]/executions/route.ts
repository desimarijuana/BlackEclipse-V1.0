import { NextResponse } from "next/server";
import { getOrCreateProfile, listTradeExecutions } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/trades/[id]/executions — the trade's execution log
// (created / entry_modified / stop_modified / target_modified / partial_exit…).
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const executions = await listTradeExecutions(profileId, id);
    return NextResponse.json({ executions });
  } catch (err) {
    console.error("[api/journal/trades/executions] GET error:", err);
    return NextResponse.json({ error: "Failed to load executions" }, { status: 500 });
  }
}
