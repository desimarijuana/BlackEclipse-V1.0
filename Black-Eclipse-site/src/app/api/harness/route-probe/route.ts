import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runRouteHealthProbe } from "@/lib/harness/route-probe";

export const dynamic = "force-dynamic";

// POST /api/harness/route-probe — the MANUAL one-shot cross-market route-health
// probe (Harness closeout Phase 2.5). Operator-gated by `guardMutation` (loopback
// or CRON_SECRET); it records one attempt per (market × implemented capability)
// into the SAME SourceHealth ledger. The recurring schedule is separately gated
// behind `HARNESS_ROUTE_PROBE_ENABLED` and is OFF by default.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "route-probe");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as {
      markets?: unknown;
      kind?: unknown;
      timeoutMs?: unknown;
    };
    const kind = body.kind === "fixture" ? "fixture" : "live";
    const markets = Array.isArray(body.markets) ? (body.markets as string[]) : undefined;
    const timeoutMs = typeof body.timeoutMs === "number" ? body.timeoutMs : undefined;
    const result = await runRouteHealthProbe({ kind, markets, timeoutMs });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    console.error("[api/harness/route-probe] POST error:", err);
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "probe failed" },
      { status: 500 }
    );
  }
}
