import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { loadPriceHistory } from "@/lib/investor-eye/phase2";
import { computePriceReaction } from "@/lib/investor-eye/reaction";
import { rowToEvent } from "@/lib/investor-eye/state";
import { countryByIso2 } from "@/lib/investor-eye/countries";
import { HISTORY_UNIVERSE } from "@/lib/investor-eye/history";

export const dynamic = "force-dynamic";

/**
 * Resolve the instrument whose stored history best represents an event when the
 * caller names none: the primary affected country's index, else the first
 * symbol we actually track. Mirrors the analogues route so both panels agree.
 */
function resolveSymbol(countries: string[], requested?: string | null): string | undefined {
  if (requested) return requested;
  for (const iso2 of countries) {
    const def = countryByIso2(iso2);
    if (!def?.marketId) continue;
    const hit = HISTORY_UNIVERSE.find((e) => e.market === def.marketId);
    if (hit) return hit.symbol;
  }
  // Commodity-linked events are the ones users ask about most; fall back to the
  // commodity futures we track only when the text implies energy/materials.
  return undefined;
}

/**
 * GET /api/investor-eye/reaction?id=<eventId>&symbol=<asset>
 *
 * How did the relevant market actually move AFTER this event? Returns measured
 * close-to-close returns for real stored candles, or an honest UNAVAILABLE.
 * Never a synthetic series, never a prediction.
 */
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
      return NextResponse.json({ available: false, note: "Event not found." });
    }

    const resolved = resolveSymbol(target.countries, symbol);
    if (!resolved) {
      return NextResponse.json({
        available: false,
        note: "No instrument with stored history is linked to this event's countries.",
        countries: target.countries,
      });
    }

    // Pull enough history to cover the event regardless of how old it is.
    const ageDays = Math.max(
      30,
      Math.ceil((Date.now() - Date.parse(target.publishedAt)) / (24 * 60 * 60 * 1000)) + 40,
    );
    const series = await loadPriceHistory(resolved, Math.min(ageDays, 365 * 3));
    const reaction = computePriceReaction(resolved, target.publishedAt, series);

    return NextResponse.json({
      available: reaction.measures.length > 0,
      reaction,
      symbol: resolved,
      eventDate: reaction.baseline?.date ?? null,
      countries: target.countries,
    });
  } catch (err) {
    console.error("[api/investor-eye/reaction] error:", err);
    return NextResponse.json({ available: false, note: "Price reaction unavailable." });
  }
}
