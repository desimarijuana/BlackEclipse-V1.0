import { NextResponse } from "next/server";
import { getFundamentals } from "@/lib/fundamentals";
import { rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
// Provider fetches (SEC filings + a Python round-trip) can take a while; allow
// the route room without hitting the platform's default function timeout.
export const maxDuration = 60;

/**
 * GET /api/fundamentals?symbol=AAPL&market=US[&refresh=1]
 *
 * Provider → Normalization → JDDS → UI. The route owns provider selection and
 * caching; the client only renders the normalized Eclipse snapshot. When no
 * provider can serve the symbol the response is an explicit `available: false`
 * state — never fabricated figures.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const symbol = url.searchParams.get("symbol")?.trim().toUpperCase();
  const market = (url.searchParams.get("market") ?? "US").trim().toUpperCase();
  const force = url.searchParams.get("refresh") === "1";

  if (!symbol) {
    return NextResponse.json(
      { available: false, symbol: null, market, reason: "A symbol is required." },
      { status: 400 },
    );
  }

  const rl = rateLimit(`fundamentals:${clientKey(request)}`, { limit: 40, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { available: false, symbol, market, reason: "Too many requests — slow down." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSec) } },
    );
  }

  try {
    const snapshot = await getFundamentals(symbol, market, { force });
    if (!snapshot) {
      return NextResponse.json(
        {
          available: false,
          symbol,
          market,
          reason: "No fundamentals provider returned data for this symbol.",
        },
        { status: 200 },
      );
    }
    return NextResponse.json({ available: true, ...snapshot });
  } catch (err) {
    console.error("[api/fundamentals] error:", err);
    return NextResponse.json(
      {
        available: false,
        symbol,
        market,
        reason: "Fundamentals fetch failed.",
      },
      { status: 200 },
    );
  }
}
