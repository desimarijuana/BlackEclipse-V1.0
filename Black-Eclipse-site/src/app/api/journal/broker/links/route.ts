import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile } from "@/lib/journal/data";
import { createBrokerLink, listBrokerLinks } from "@/lib/journal/broker/links";

export const dynamic = "force-dynamic";

// GET /api/journal/broker/links — journal ↔ broker links for this profile.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const links = await listBrokerLinks(profileId);
    return NextResponse.json({ links });
  } catch (err) {
    console.error("[api/journal/broker/links] GET error:", err);
    return NextResponse.json({ error: "Failed to load broker links" }, { status: 500 });
  }
}

// POST /api/journal/broker/links — connect a broker connection to the journal.
// Body: { connectionId, accountId?, enabled?, autoSync?, backfillDays?, symbolMap? }
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-broker-link");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const connectionId = typeof body.connectionId === "string" ? body.connectionId : "";
    if (!connectionId.trim()) {
      return NextResponse.json({ error: "connectionId is required" }, { status: 400 });
    }
    const profileId = await getOrCreateProfile();
    const link = await createBrokerLink(profileId, {
      connectionId,
      accountId: typeof body.accountId === "string" ? body.accountId : null,
      enabled: body.enabled !== false,
      autoSync: body.autoSync === true,
      backfillDays: typeof body.backfillDays === "number" ? body.backfillDays : undefined,
      symbolMap:
        body.symbolMap && typeof body.symbolMap === "object" && !Array.isArray(body.symbolMap)
          ? (body.symbolMap as Record<string, string>)
          : null,
    });
    return NextResponse.json({ success: true, link });
  } catch (err) {
    console.error("[api/journal/broker/links] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create broker link" },
      { status: 500 },
    );
  }
}
