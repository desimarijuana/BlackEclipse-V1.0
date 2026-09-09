import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { runJournalAgent } from "@/lib/agent/journal";
import { getOrCreateProfile, saveAiReview } from "@/lib/journal/data";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// POST /api/journal/agent — run the journal agent.
// Body: { query: string, tradeId?: string, start?: string, end?: string }
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "journal-agent", { limit: 10, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const query = typeof body.query === "string" ? body.query.trim() : "";
    if (!query) {
      return NextResponse.json({ error: "query is required" }, { status: 400 });
    }
    if (query.length > 500) {
      return NextResponse.json({ error: "query too long (max 500 chars)" }, { status: 400 });
    }
    const tradeId = typeof body.tradeId === "string" ? body.tradeId : undefined;
    const start = typeof body.start === "string" ? body.start : undefined;
    const end = typeof body.end === "string" ? body.end : undefined;
    const result = await runJournalAgent({ query, tradeId, start, end });

    // Persist the AI review (best-effort).
    try {
      const profileId = await getOrCreateProfile();
      await saveAiReview(profileId, {
        kind: tradeId ? "trade" : start && end ? "weekly" : "ai",
        title: tradeId ? `AI Trade Review` : start && end ? `AI Weekly Review ${start}–${end}` : "AI Journal Analysis",
        body: result.answer,
        tradeId,
        periodStart: start,
        periodEnd: end,
      });
    } catch { /* persistence is best-effort */ }

    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    console.error("[api/journal/agent] Error:", err);
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Journal agent failed" },
      { status: 500 },
    );
  }
}
