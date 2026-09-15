import { NextResponse } from "next/server";
import { assembleState } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/markets — the market layer's observations.
// Reuses the EXISTING market path (IndexQuote + the yfinance bridge via
// `assembleState`), so this is not a second market-data system.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;
  try {
    const state = await assembleState({ hours });
    return NextResponse.json({
      markets: state.markets,
      total: state.markets.length,
      provenance: state.status.provenance,
      updatedAt: state.status.updatedAt,
    });
  } catch (err) {
    console.error("[api/investor-eye/markets] error:", err);
    return NextResponse.json({ markets: [], total: 0, provenance: "UNAVAILABLE", updatedAt: null });
  }
}
