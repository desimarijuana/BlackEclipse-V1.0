import { NextResponse } from "next/server";
import { assembleState, isAssembling } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/state — the assembled world state.
//
// This is the single payload the globe visualizes: normalized events, country
// summaries (events + markets), market observations, and honest provenance.
// It is cached server-side (SWR); pass `?refresh=1` to force a rebuild (still
// safe: a rebuild returns the current state immediately and finishes in the
// background if one is already running).
//
// Query params:
//   ?hours=1|6|24|168|720   time window (default 24)
//   ?refresh=1              force a rebuild
//   ?limit=<n>              max records per source (bounded)
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;
  const force = searchParams.get("refresh") === "1";
  const limitRaw = Number(searchParams.get("limit") ?? "75");
  const maxRecordsPerSource = Number.isFinite(limitRaw) ? Math.max(5, Math.min(limitRaw, 200)) : 75;

  try {
    const state = await assembleState({ hours, force, maxRecordsPerSource });
    return NextResponse.json(state);
  } catch (err) {
    console.error("[api/investor-eye/state] error:", err);
    // Never 500 the globe — return an honest empty/UNAVAILABLE state.
    return NextResponse.json(
      {
        generatedAt: new Date().toISOString(),
        windowHours: hours,
        events: [],
        countries: [],
        markets: [],
        eventsUnavailable: true,
        status: {
          provenance: "UNAVAILABLE",
          updatedAt: null,
          label: "DATA UNAVAILABLE",
          sources: [],
        },
        assembling: isAssembling(),
      },
      { status: 200 },
    );
  }
}
