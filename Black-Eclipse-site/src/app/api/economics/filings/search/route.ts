import { NextResponse } from "next/server";
import { searchEdgarFilings } from "@/lib/economics/edgar-search";
import { rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// GET /api/economics/filings/search?q=inflation&forms=8-K,10-K&start=2026-01-01&end=2026-11-09
// Official EDGAR full-text search across every filing. `q` is required; forms
// and the date window are optional. Results are normalized to the same filing
// shape the latest-filings route returns.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const query = (url.searchParams.get("q") ?? "").trim();
  const forms = (url.searchParams.get("forms") ?? "").trim();
  const start = (url.searchParams.get("start") ?? "").trim();
  const end = (url.searchParams.get("end") ?? "").trim();
  const rawLimit = Number(url.searchParams.get("limit"));
  const limit = Number.isFinite(rawLimit) ? rawLimit : 40;
  const refresh = url.searchParams.get("refresh") === "1";

  if (query.length < 2) {
    return NextResponse.json({ filings: [], total: 0, error: "Enter at least two characters to search." }, { status: 400 });
  }
  if (query.length > 200) {
    return NextResponse.json({ filings: [], total: 0, error: "Search query is too long." }, { status: 400 });
  }
  if ((start && !end) || (!start && end)) {
    return NextResponse.json({ filings: [], total: 0, error: "Provide both start and end dates, or neither." }, { status: 400 });
  }

  const rl = rateLimit(`econ-filings-search:${clientKey(request)}`, { limit: 20, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { filings: [], total: 0, error: "Too many searches — slow down." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSec) } },
    );
  }

  try {
    const result = await searchEdgarFilings({ query, forms, start, end, limit, refresh });
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const clientError = /query must|too long|invalid form|must be YYYY-MM-DD/.test(message);
    console.error("[api/economics/filings/search] error:", message);
    return NextResponse.json(
      { filings: [], total: 0, error: clientError ? message : "EDGAR full-text search is unavailable right now." },
      { status: clientError ? 400 : 502 },
    );
  }
}
