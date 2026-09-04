import { NextResponse } from "next/server";
import { fetchEconomicCalendar } from "@/lib/economics/calendar";

export const dynamic = "force-dynamic";

// In-memory SWR cache — the calendar moves slowly, serve instantly and
// refresh in the background (same pattern as /api/global-overview).
const CACHE_TTL_MS = 10 * 60 * 1000;
let cache: { t: number; data: Awaited<ReturnType<typeof fetchEconomicCalendar>> } | null = null;
let rebuildInFlight = false;

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  fetchEconomicCalendar()
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
    const data = await fetchEconomicCalendar();
    cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/economics/calendar] GET error:", err);
    return NextResponse.json({ events: [], source: "error" }, { status: 500 });
  }
}