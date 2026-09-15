import { NextResponse } from "next/server";
import { queryEvents } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/events — persisted, filtered event feed.
// Query params: hours, country (ISO2), type, severity, limit.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;
  const limitRaw = Number(searchParams.get("limit") ?? "800");
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(limitRaw, 2000)) : 800;

  try {
    const events = await queryEvents({
      hours,
      limit,
      iso2: searchParams.get("country") ?? undefined,
      eventType: searchParams.get("type") ?? undefined,
      severity: searchParams.get("severity") ?? undefined,
    });
    return NextResponse.json({ events, total: events.length, windowHours: hours });
  } catch (err) {
    console.error("[api/investor-eye/events] error:", err);
    return NextResponse.json({ events: [], total: 0, windowHours: hours, error: "unavailable" });
  }
}
