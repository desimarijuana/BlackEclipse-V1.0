import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// GET /api/markets/global — global market index overview.
// The live index-quote feed was removed with the scraper subsystem, so this
// returns an empty list. The Markets tab falls back to its empty state.
export async function GET() {
  return NextResponse.json({ markets: [], total: 0 });
}
