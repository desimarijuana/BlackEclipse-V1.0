import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { loadPriorEventsOfType, loadPriceHistory } from "@/lib/investor-eye/phase2";
import { buildAnalogues } from "@/lib/investor-eye/analytics";
import { rowToEvent } from "@/lib/investor-eye/state";
import { countryByIso2 } from "@/lib/investor-eye/countries";
import { HISTORY_UNIVERSE } from "@/lib/investor-eye/history";

export const dynamic = "force-dynamic";

/**
 * Pick the instrument whose history best represents an event, when the caller
 * did not name one: the primary affected country's index, else the first
 * symbol we actually track history for. Never guesses a ticker we have no
 * candles for — the panel then honestly reports UNAVAILABLE.
 */
function resolveSymbol(countries: string[], requested?: string | null): string | undefined {
  if (requested) return requested;
  for (const iso2 of countries) {
    const def = countryByIso2(iso2);
    if (!def?.marketId) continue;
    const hit = HISTORY_UNIVERSE.find((e) => e.market === def.marketId);
    if (hit) return hit.symbol;
  }
  return undefined;
}

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
    const resolved = resolveSymbol(target.countries, symbol);
    const series = resolved ? await loadPriceHistory(resolved, 365 * 3) : undefined;
    const analogues = buildAnalogues(target, priorEvents, series, resolved);
    return NextResponse.json({
      available: true,
      analogues,
      // Present so the UI can explain WHY a series is missing.
      symbol: resolved ?? null,
      countries: target.countries,
    });
  } catch (err) {
    console.error("[api/investor-eye/analogues] error:", err);
    return NextResponse.json({ available: false, note: "Historical data unavailable." });
  }
}
