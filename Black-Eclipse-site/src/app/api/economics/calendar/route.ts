import { NextResponse } from "next/server";
import { fetchEconomicCalendar, filterUpcoming, type EconomicCalendar } from "@/lib/economics/calendar";
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

// GET /api/economics/calendar?days=30 — upcoming releases with
// actual/forecast/previous. `days=all` removes the upper bound. The cached
// payload is always the full feed; filtering happens per request.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const rawDays = url.searchParams.get("days");
  const force = url.searchParams.get("refresh") === "1";
  const past = url.searchParams.get("past") === "1";
  let days: number | null = 30;
  if (rawDays === "all" || rawDays === "0") {
    days = null;
  } else if (rawDays !== null) {
    const parsed = Number(rawDays);
    days = Number.isFinite(parsed) && parsed > 0 && parsed <= 365 ? parsed : 30;
  }
  const respond = (data: EconomicCalendar) =>
    NextResponse.json({ ...data, events: filterUpcoming(data.events, { days, past }), days: days ?? "all", past });

  try {
    if (!force && cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) return respond(cache.data);
      startBackgroundRebuild();
      return respond(cache.data);
    }
    const data = await finalize(await fetchEconomicCalendar());
    cache = { t: Date.now(), data };
    return respond(data);
  } catch (err) {
    console.error("[api/economics/calendar] GET error:", err);
    const last = await readLastGood<EconomicCalendar>("calendar");
    if (last?.data?.events?.length) {
      return respond({ ...last.data, source: "cached" });
    }
    return NextResponse.json({ events: [], source: "unavailable", warnings: [], days: days ?? "all", past }, { status: 200 });
  }
}
