import { NextResponse } from "next/server";
import { fetchEconomicCalendar, type EconomicCalendar } from "@/lib/economics/calendar";
import { readLastGood, writeLastGood } from "@/lib/economics/state-cache";

export const dynamic = "force-dynamic";

// In-memory SWR cache — the calendar moves slowly, serve instantly and
// refresh in the background (same pattern as /api/global-overview).
const CACHE_TTL_MS = 10 * 60 * 1000;
let cache: { t: number; data: EconomicCalendar } | null = null;
let rebuildInFlight = false;

/**
 * Persist a good calendar, or fall back to the last good one when every source
 * is down. A cached calendar is labelled `cached` — it is still real dates, not
 * a synthetic schedule.
 */
async function finalize(data: EconomicCalendar): Promise<EconomicCalendar> {
  if (data.events.length > 0) {
    await writeLastGood("calendar", data);
    return data;
  }
  const last = await readLastGood<EconomicCalendar>("calendar");
  if (last?.data?.events?.length) {
    return {
      ...last.data,
      source: "cached",
      warnings: [
        ...data.warnings,
        `serving last good calendar from ${last.savedAt.slice(0, 10)}`,
      ],
    };
  }
  return data;
}

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  fetchEconomicCalendar()
    .then(finalize)
    .then((data) => { cache = { t: Date.now(), data }; })
    .catch((err) => console.error("[api/economics/calendar] background rebuild:", err))
    .finally(() => { rebuildInFlight = false; });
}

// GET /api/economics/calendar — upcoming releases with actual/forecast/previous.
export async function GET() {
  try {
    if (cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) return NextResponse.json(cache.data);
      startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    const data = await finalize(await fetchEconomicCalendar());
    cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/economics/calendar] GET error:", err);
    const last = await readLastGood<EconomicCalendar>("calendar");
    if (last?.data?.events?.length) {
      return NextResponse.json({ ...last.data, source: "cached" });
    }
    return NextResponse.json({ events: [], source: "unavailable", warnings: [] }, { status: 200 });
  }
}
