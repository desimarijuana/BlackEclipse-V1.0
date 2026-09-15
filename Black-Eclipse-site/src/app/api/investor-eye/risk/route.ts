import { NextResponse } from "next/server";
import { assembleState } from "@/lib/investor-eye/state";
import { buildRiskState, buildRegionState, buildTransmissions } from "@/lib/investor-eye/analytics";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/risk — decomposable risk dimensions + region state +
// market transmissions. Every component carries its drivers and sample size so
// no number is presented without its evidence (spec §39).
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;
  try {
    const state = await assembleState({ hours });
    return NextResponse.json({
      generatedAt: state.generatedAt,
      windowHours: state.windowHours,
      components: buildRiskState(state.events),
      regions: buildRegionState(state.events, state.countries),
      transmissions: buildTransmissions(state.events, state.markets),
      eventCount: state.events.length,
      provenance: state.status.provenance,
    });
  } catch (err) {
    console.error("[api/investor-eye/risk] error:", err);
    return NextResponse.json({
      components: [], regions: [], transmissions: [], eventCount: 0, provenance: "UNAVAILABLE",
    });
  }
}
