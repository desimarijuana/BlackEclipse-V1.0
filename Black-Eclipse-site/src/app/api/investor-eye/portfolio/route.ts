import { NextResponse } from "next/server";
import { assembleState } from "@/lib/investor-eye/state";
import { computeExposure, portfolioIntersections, type HoldingLike } from "@/lib/investor-eye/analytics";

export const dynamic = "force-dynamic";

// POST /api/investor-eye/portfolio
// Body: { holdings: [{ symbol, weight, country?, sector? }] }
//
// The CLIENT owns portfolio valuation (the existing portfolio engine); this
// endpoint only computes exposure and event intersections from whatever
// holdings it receives. It never returns advice, and it never invents a
// country/sector for a holding that did not supply one.
export async function POST(request: Request) {
  let holdings: HoldingLike[] = [];
  try {
    const body = (await request.json()) as { holdings?: unknown };
    if (Array.isArray(body.holdings)) {
      holdings = body.holdings
        .filter((h): h is Record<string, unknown> => Boolean(h) && typeof h === "object")
        .map((h) => ({
          symbol: String(h.symbol ?? ""),
          weight: Number(h.weight ?? 0),
          country: h.country ? String(h.country).toUpperCase() : undefined,
          sector: h.sector ? String(h.sector) : undefined,
        }))
        .filter((h) => h.symbol.length > 0 && Number.isFinite(h.weight));
    }
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }

  try {
    const exposure = computeExposure(holdings);
    const state = await assembleState({ hours: 168 });
    const intersections = portfolioIntersections(state.events, exposure);
    return NextResponse.json({
      exposure,
      intersections,
      intersectionCount: intersections.length,
      windowHours: state.windowHours,
      provenance: state.status.provenance,
      disclaimer: "Exposure relationships only — this is not investment advice or a recommendation.",
    });
  } catch (err) {
    console.error("[api/investor-eye/portfolio] error:", err);
    return NextResponse.json({
      exposure: { countries: [], sectors: [], total: 0, unmappedWeight: 0 },
      intersections: [], intersectionCount: 0, provenance: "UNAVAILABLE",
      disclaimer: "Exposure unavailable.",
    });
  }
}
