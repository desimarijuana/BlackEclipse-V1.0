import { NextResponse } from "next/server";
import { getOrCreateProfile } from "@/lib/journal/data";
import { previewJournalBroker } from "@/lib/journal/broker/sync";

export const dynamic = "force-dynamic";

// GET /api/journal/broker/preview?connectionId=... — read-only dry run.
// Refresh the broker mirror first with POST /api/trading/connections/{id}/sync;
// this route never writes a broker or journal row.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const connectionId = (searchParams.get("connectionId") ?? "").trim();
  if (!connectionId) {
    return NextResponse.json({ error: "connectionId is required" }, { status: 400 });
  }
  try {
    const profileId = await getOrCreateProfile();
    const preview = await previewJournalBroker(profileId, connectionId);
    return NextResponse.json(preview);
  } catch (err) {
    console.error("[api/journal/broker/preview] GET error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Preview failed" },
      { status: 500 },
    );
  }
}
