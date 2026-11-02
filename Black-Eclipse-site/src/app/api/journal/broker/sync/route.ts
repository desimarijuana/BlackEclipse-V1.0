import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { getOrCreateProfile } from "@/lib/journal/data";
import { syncJournalBroker } from "@/lib/journal/broker/sync";

export const dynamic = "force-dynamic";

// POST /api/journal/broker/sync — refresh the broker mirror and project its
// deals into the journal. Idempotent: broker trades are keyed by externalId.
// Body: { connectionId: string }
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "journal-broker-sync", {
    limit: 6,
    windowMs: 60_000,
  });
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  try {
    const body = await request.json().catch(() => ({}));
    const connectionId = typeof body.connectionId === "string" ? body.connectionId.trim() : "";
    if (!connectionId) {
      return NextResponse.json({ error: "connectionId is required" }, { status: 400 });
    }
    const profileId = await getOrCreateProfile();
    const summary = await syncJournalBroker(profileId, connectionId);
    // A broker that is down is a completed, honest result — not a server crash.
    return NextResponse.json(summary);
  } catch (err) {
    console.error("[api/journal/broker/sync] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Broker sync failed" },
      { status: 500 },
    );
  }
}
