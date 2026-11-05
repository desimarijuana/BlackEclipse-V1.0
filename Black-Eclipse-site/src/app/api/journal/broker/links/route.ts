import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { requireOperatorApiAuth } from "@/lib/auth/server";
import { getOrCreateProfile } from "@/lib/journal/data";
import {
  BrokerLinkInputError,
  createBrokerLink,
  listBrokerLinks,
} from "@/lib/journal/broker/links";
import { isValidBrokerConnectionId } from "@/lib/journal/broker/ownership";
import { BrokerSourceUnavailable, getBrokerConnection } from "@/lib/journal/broker/source";

export const dynamic = "force-dynamic";

// GET /api/journal/broker/links — journal ↔ broker links for this profile.
export async function GET(request: Request) {
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
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
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
  const blocked = guardMutation(request, "journal-broker-link");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const connectionId = typeof body.connectionId === "string" ? body.connectionId.trim() : "";
    if (!isValidBrokerConnectionId(connectionId)) {
      return NextResponse.json({ error: "A valid connectionId is required" }, { status: 400 });
    }

    // Only link a connection the runtime actually knows about.
    try {
      await getBrokerConnection(connectionId);
    } catch (err) {
      if (err instanceof BrokerSourceUnavailable && err.code === "RUNTIME_UNAVAILABLE") {
        return NextResponse.json(
          { error: "The broker runtime is unavailable, so the connection cannot be verified" },
          { status: 503 },
        );
      }
      return NextResponse.json(
        { error: "Unknown broker connection. Create it in the broker panel first." },
        { status: 400 },
      );
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
    if (err instanceof BrokerLinkInputError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json({ error: "Failed to create broker link" }, { status: 500 });
  }
}
