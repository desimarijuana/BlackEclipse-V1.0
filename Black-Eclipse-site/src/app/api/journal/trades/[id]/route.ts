import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, updateTrade, deleteTrade } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// PATCH /api/journal/trades/[id] — update a trade (recomputes metrics, logs an
// execution event). Body: partial UpdateTradeInput.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-trades-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const trade = await updateTrade(profileId, id, body);
    if (!trade) return NextResponse.json({ error: "Trade not found" }, { status: 404 });
    return NextResponse.json({ success: true, trade });
  } catch (err) {
    console.error("[api/journal/trades] PATCH error:", err);
    const status = (err as { status?: unknown }).status;
    // 409 is the deliberate broker-ownership refusal; everything else is
    // internal and must not leak a Prisma message to the client.
    if (status === 409) {
      return NextResponse.json(
        { error: err instanceof Error ? err.message : "This trade is broker-owned" },
        { status: 409 },
      );
    }
    return NextResponse.json({ error: "Failed to update trade" }, { status: 500 });
  }
}

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
      { status: 500 },
    );
  }
}
