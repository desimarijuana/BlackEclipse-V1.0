import { NextResponse } from "next/server";
import { assembleState } from "@/lib/investor-eye/state";
import { planQuery, scoreEventAgainstPlan } from "@/lib/investor-eye/analytics";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/query?q=what%20is%20affecting%20oil
//
// Deterministic natural-language map search (spec §43). No LLM on the query
// path — the plan is derived from keywords and the country gazetteer, exactly
// like the command palette's grammar (ADR-009). The client applies the plan to
// map state; this route returns the plan plus the ranked matching events so the
// UI has something concrete to highlight.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = (searchParams.get("q") ?? "").trim();
  if (!q) {
    return NextResponse.json({ plan: null, matches: [], error: "missing_query" }, { status: 400 });
  }
  try {
    const plan = planQuery(q);
    const state = await assembleState({ hours: 168 });
    const matches = state.events
      .map((e) => ({ event: e, score: scoreEventAgainstPlan(e, plan) }))
      .filter((m) => m.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 50)
      .map((m) => m.event);
    return NextResponse.json({ plan, matches, matchCount: matches.length });
  } catch (err) {
    console.error("[api/investor-eye/query] error:", err);
    return NextResponse.json({ plan: planQuery(q), matches: [], matchCount: 0 });
  }
}
