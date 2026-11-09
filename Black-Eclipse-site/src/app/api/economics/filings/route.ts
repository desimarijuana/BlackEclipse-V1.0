import { NextResponse } from "next/server";
import { fetchLatestFilings, isPlausibleForm } from "@/lib/economics/sec-filings-feed";
import { rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// GET /api/economics/filings?form=8-K&limit=40
// Market-wide EDGAR current-events feed, official and keyless. `form` is an
// optional exact form type; omitting it returns the unfiltered latest feed.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const form = (url.searchParams.get("form") ?? "").trim();
  const rawLimit = Number(url.searchParams.get("limit"));
  const limit = Number.isFinite(rawLimit) ? rawLimit : 40;

  if (form && !isPlausibleForm(form)) {
    return NextResponse.json({ filings: [], error: "form is not a plausible SEC form type." }, { status: 400 });
  }

  const rl = rateLimit(`econ-filings:${clientKey(request)}`, { limit: 30, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { filings: [], error: "Too many filing requests — slow down." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSec) } },
    );
  }

  try {
    const result = await fetchLatestFilings({ form, limit });
    return NextResponse.json(result);
  } catch (error) {
    console.error("[api/economics/filings] error:", error);
    return NextResponse.json(
      { filings: [], form, error: "The SEC filings feed is unavailable right now." },
      { status: 502 },
    );
  }
}
