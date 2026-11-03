import { NextResponse } from "next/server";
import { clientKey, rateLimit } from "@/lib/api-guard";
import { requireOperatorApiAuth } from "@/lib/auth/server";
import { getOrCreateProfile } from "@/lib/journal/data";
import { isValidBrokerConnectionId } from "@/lib/journal/broker/ownership";
import { previewJournalBroker } from "@/lib/journal/broker/sync";

export const dynamic = "force-dynamic";

// GET /api/journal/broker/preview?connectionId=... — read-only dry run.
// Refresh the broker mirror first with POST /api/trading/connections/{id}/sync;
// this route never writes a broker or journal row.
export async function GET(request: Request) {
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
  // A preview reads the whole mirror and can spawn the runtime; it must not be
  // a free request loop from a tab or a script.
  const limited = rateLimit(`journal-broker-preview:${clientKey(request)}`, {
    limit: 12,
    windowMs: 60_000,
  });
  if (!limited.ok) {
    return NextResponse.json(
      { error: "Too many preview requests; try again shortly" },
      { status: 429, headers: { "Retry-After": String(limited.retryAfterSec) } },
    );
  }
  const { searchParams } = new URL(request.url);
  const connectionId = (searchParams.get("connectionId") ?? "").trim();
  if (!isValidBrokerConnectionId(connectionId)) {
    return NextResponse.json({ error: "A valid connectionId is required" }, { status: 400 });
  }
  try {
    const profileId = await getOrCreateProfile();
    const preview = await previewJournalBroker(profileId, connectionId);
    return NextResponse.json(preview);
  } catch (err) {
    console.error("[api/journal/broker/preview] GET error:", err);
    return NextResponse.json({ error: "Broker preview failed" }, { status: 500 });
  }
}
