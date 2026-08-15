import { NextResponse } from "next/server";
import { runResearch } from "@/lib/agent/research";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// POST /api/agent/research — run the multi-agent research engine.
// Body: { query: string, ticker?: string, market?: string }
export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const query = typeof body.query === "string" ? body.query.trim() : "";
    if (!query) {
      return NextResponse.json({ error: "query is required" }, { status: 400 });
    }

    const result = await runResearch({
      query,
      ticker: typeof body.ticker === "string" ? body.ticker : undefined,
      market: typeof body.market === "string" ? body.market : undefined,
    });

    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    console.error("[api/agent/research] Error:", err);
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Research failed" },
      { status: 500 }
    );
  }
}
