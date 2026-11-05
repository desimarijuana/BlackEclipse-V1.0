import { NextResponse } from "next/server";
import { getOrCreateProfile, listTradeFills } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/trades/[id]/fills — the broker deals projected into a trade.
// Empty for manual/CSV/demo trades; a broker trade can have several (scale-ins,
// partial closes, multi-fill exits).
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const fills = await listTradeFills(profileId, id);
    return NextResponse.json({ fills });
  } catch (err) {
    console.error("[api/journal/trades/fills] GET error:", err);
    return NextResponse.json({ error: "Failed to load broker fills" }, { status: 500 });
  }
}
