import { NextResponse } from "next/server";
import { triggerNewsIngest } from "@/lib/scraper/scheduler";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
// Ingestion fetches ~55 feeds over the network; give it room to finish.
export const maxDuration = 60;

/**
 * POST /api/cron/refresh-news — trigger one news ingestion cycle on demand
 * (used by the news page's refresh button). Concurrency-guarded: if a cycle
 * is already running, returns immediately with running=true.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "refresh-news");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    await triggerNewsIngest();
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/cron/refresh-news] Error:", err);
    return NextResponse.json({ error: "News refresh failed" }, { status: 500 });
  }
}