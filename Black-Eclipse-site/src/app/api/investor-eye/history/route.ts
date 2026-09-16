import { NextResponse } from "next/server";
import { backfillMarketHistory, historyStatus, isBackfilling } from "@/lib/investor-eye/history";
import { checkMutationAllowed, rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/history — how much daily history each tracked index has.
// Used by the UI to explain why an analogue series is or isn't available.
export async function GET() {
  try {
    const status = await historyStatus();
    const covered = status.filter((s) => s.bars >= 30).length;
    return NextResponse.json({
      symbols: status,
      covered,
      total: status.length,
      busy: isBackfilling(),
    });
  } catch (err) {
    console.error("[api/investor-eye/history] error:", err);
    return NextResponse.json({ symbols: [], covered: 0, total: 0, busy: false });
  }
}

// POST /api/investor-eye/history — warm the candle cache from the existing
// yfinance bridge. Guarded + rate-limited: it performs real outbound fetches.
export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) {
    return NextResponse.json({ error: guard.reason }, { status: 403 });
  }
  const rl = rateLimit(`investor-eye:history:${clientKey(request)}`, { limit: 3, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json({ error: "rate_limited", retryAfterSec: rl.retryAfterSec }, {
      status: 429,
      headers: { "Retry-After": String(rl.retryAfterSec) },
    });
  }
  try {
    const result = await backfillMarketHistory();
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    console.error("[api/investor-eye/history] backfill error:", err);
    return NextResponse.json({ ok: false, error: "unavailable" });
  }
}
