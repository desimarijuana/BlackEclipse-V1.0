import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { loadPriorEventsOfType, loadPriceHistory } from "@/lib/investor-eye/phase2";
import { buildAnalogues } from "@/lib/investor-eye/analytics";
import { rowToEvent } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/analogues?id=<eventId>&symbol=<asset>
// Returns real historical context for an event: prior periods of the same event
// type, plus the actual stored price series for the requested asset. Never a
// synthetic curve, never a prediction — see the `disclaimer` field.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");
  const symbol = searchParams.get("symbol");

  try {
    let target = null as ReturnType<typeof rowToEvent> | null;
    if (id) {
      const row = await prisma.geopoliticalEvent.findFirst({ where: { OR: [{ id }, { dedupKey: id }] } });
      if (row) target = rowToEvent(row);
    }
    if (!target) {
      // No event specified — fall back to the most recent event of any type.
      const row = await prisma.geopoliticalEvent.findFirst({ orderBy: { publishedAt: "desc" } });
      if (row) target = rowToEvent(row);
    }
    if (!target) {
      return NextResponse.json({
        available: false,
        note: "No events have been ingested yet.",
      });
    }

    const priorEvents = await loadPriorEventsOfType(target.eventType, 36);
    const series = symbol ? await loadPriceHistory(symbol, 365 * 3) : undefined;
    const analogues = buildAnalogues(target, priorEvents, series, symbol ?? undefined);
    return NextResponse.json({ available: true, analogues });
  } catch (err) {
    console.error("[api/investor-eye/analogues] error:", err);
    return NextResponse.json({ available: false, note: "Historical data unavailable." });
  }
}
