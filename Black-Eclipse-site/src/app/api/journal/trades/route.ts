import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, createTrade, loadTrades } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/trades — list trades for the profile.
//
// Query parameters are part of the contract because the agent's `app_api_get`
// tool calls this route directly. This GET used to ignore them and always
// serialise every trade (~100 KB for 119 trades), so `?limit=1`, `?status=open`
// and `?take=10` all returned the same payload. The agent kept retrying,
// burned its step budget, and the run ended without an answer.
//
// `limit`/`take` bound the rows; `status` and `symbol` filter them. Filtering
// happens before the limit so `?status=open&limit=5` means five OPEN trades.
// The default (no parameters) is unchanged: all trades.
export async function GET(request: Request) {
  try {
    const profileId = await getOrCreateProfile();
    let trades = await loadTrades(profileId);
    const total = trades.length;

    const url = request && typeof request.url === "string" ? new URL(request.url) : null;
    const params = url?.searchParams;
    const rawLimit = params?.get("limit") ?? params?.get("take") ?? null;
    const status = (params?.get("status") || "").trim().toLowerCase();
    const symbol = (params?.get("symbol") || "").trim().toUpperCase();

    if (status) {
      trades = trades.filter(
        (trade) => String((trade as { status?: unknown }).status ?? "").trim().toLowerCase() === status,
      );
    }
    if (symbol) {
      trades = trades.filter(
        (trade) => String((trade as { symbol?: unknown }).symbol ?? "").trim().toUpperCase() === symbol,
      );
    }

    let limit: number | null = null;
    if (rawLimit !== null && rawLimit !== "") {
      const parsed = Number.parseInt(rawLimit, 10);
      if (Number.isFinite(parsed) && parsed > 0) {
        limit = Math.min(parsed, 1000);
      }
    }
    if (limit !== null) trades = trades.slice(0, limit);

    return NextResponse.json({ trades, count: trades.length, total });
  } catch (err) {
    console.error("[api/journal/trades] GET error:", err);
    return NextResponse.json({ error: "Failed to load trades" }, { status: 500 });
  }
}

// POST /api/journal/trades — create a trade.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-trades");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const trade = await createTrade(profileId, body);
    return NextResponse.json({ success: true, trade });
  } catch (err) {
    console.error("[api/journal/trades] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create trade" },
      { status: 500 }
    );
  }
}
