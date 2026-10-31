// ── /api/workflow-schedules/[sid]/run — fire one schedule now ────────────────
// An explicit operator action from the schedule panel. It ignores the clock but
// keeps the same TEST-RUN envelope as a timed fire, so "Run now" can never act
// on the world just because it was clicked.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runScheduleNow } from "@/lib/graph-studio/schedule-tick";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ sid: string }> };

export async function POST(request: Request, ctx: Ctx) {
  const blocked = guardMutation(request, "workflow-schedule-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { sid } = await ctx.params;
  try {
    const outcome = await runScheduleNow(sid);
    if (outcome.action === "error") {
      return NextResponse.json({ error: outcome.error ?? "The run did not start" }, { status: 400 });
    }
    return NextResponse.json({ outcome }, { status: 201 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to run the schedule" },
      { status: 500 },
    );
  }
}
