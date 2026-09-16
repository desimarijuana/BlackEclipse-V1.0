import { NextResponse } from "next/server";
import { queryEvents } from "@/lib/investor-eye/state";
import { buildSituations, situationForEvent } from "@/lib/investor-eye/situations";

export const dynamic = "force-dynamic";

/**
 * GET /api/investor-eye/situations?event=<id>&hours=168
 *
 * Two modes:
 *   - `event` present → the situation THAT event belongs to (its recurrence in
 *     the window), for the dossier.
 *   - no `event`      → the most recurrent situations in the window, newest
 *     activity first, for an overview.
 *
 * Reads the same stored feed the map uses, so a situation can never disagree with
 * the events on screen. Recurrence is a count of real stored events — never a
 * projection.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const eventId = searchParams.get("event");
  const hoursRaw = Number(searchParams.get("hours") ?? "168");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 168;

  try {
    const events = await queryEvents({ hours, limit: 800 });

    if (eventId) {
      const target = events.find((e) => (e.id ?? e.dedupKey) === eventId);
      if (!target) {
        // The event may have aged out of the window — say so rather than
        // reporting "1 occurrence", which would understate its history.
        return NextResponse.json({ available: false, note: "Event is outside the window." });
      }
      const situation = situationForEvent(target, events);
      if (!situation) {
        return NextResponse.json({
          available: false,
          note: "This event has no place or country anchor, so recurrence cannot be grouped.",
        });
      }
      return NextResponse.json({ available: true, situation, hours });
    }

    const situations = buildSituations(events).slice(0, 12);
    return NextResponse.json({ available: situations.length > 0, situations, hours });
  } catch (err) {
    console.error("[api/investor-eye/situations] error:", err);
    return NextResponse.json({ available: false, note: "Situations unavailable." });
  }
}
