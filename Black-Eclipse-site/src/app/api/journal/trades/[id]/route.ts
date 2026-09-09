import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, deleteTrade } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// DELETE /api/journal/trades/[id] — delete a trade.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-trades-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteTrade(profileId, id);
    if (!deleted) {
      return NextResponse.json({ error: "Trade not found" }, { status: 404 });
    }
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/journal/trades] DELETE error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to delete trade" },
      { status: 500 }
    );
  }
}
