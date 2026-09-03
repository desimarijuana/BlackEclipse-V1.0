import { NextResponse } from "next/server";
import { triggerScrape, runUniverseSync } from "@/lib/scraper";
import { triggerNewsIngest } from "@/lib/scraper/scheduler";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
// A full multi-market cycle can take minutes on hosted schedulers that cut
// execution short; give it room without blocking forever.
export const maxDuration = 300;

/**
 * POST /api/cron/run — run one background maintenance cycle on demand.
 *
 * The in-process node-cron scheduler covers long-lived deployments (local dev,
 * VPS/Docker). Hosted platforms without persistent processes (Vercel) can call
 * this endpoint from a scheduler instead — vercel.json's crons entry points
 * here. Protected by the standard mutation guard: same-origin or
 * `Authorization: Bearer <CRON_SECRET>`.
 *
 * Body (all optional):
 *   { universeSync?: boolean } — also run the daily universe sync now.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "cron-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = await request.json().catch(() => ({}));
    const scrape = await triggerScrape();

    let sync: Awaited<ReturnType<typeof runUniverseSync>> | null = null;
    if (body.universeSync === true) {
      sync = await runUniverseSync();
    }

    let news: boolean = false;
    if (body.news === true) {
      await triggerNewsIngest();
      news = true;
    }

    return NextResponse.json({ success: true, scrape, sync, news });
  } catch (err) {
    console.error("[api/cron/run] Error:", err);
    return NextResponse.json({ error: "Cron cycle failed" }, { status: 500 });
  }
}

// GET /api/cron/run — convenience for schedulers that can only issue GETs.
export async function GET(request: Request) {
  const blocked = guardMutation(request, "cron-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const scrape = await triggerScrape();
    return NextResponse.json({ success: true, scrape });
  } catch (err) {
    console.error("[api/cron/run] GET Error:", err);
    return NextResponse.json({ error: "Cron cycle failed" }, { status: 500 });
  }
}
