import { NextResponse } from "next/server";
import { fetchLatestFilings, isPlausibleForm, type FilingsFeedResult } from "@/lib/economics/sec-filings-feed";
import { resolveSecTickers } from "@/lib/fundamentals/providers/sec-edgar";
import { readLastGood, writeLastGood } from "@/lib/economics/state-cache";
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
  const refresh = url.searchParams.get("refresh") === "1";
  const cacheName = `filings-feed:${form || "all"}`;

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
    const result = await fetchLatestFilings({ form, limit, refresh });
    // Best-effort ticker enrichment from the cached SEC index. A CIK without a
    // ticker stays null; enrichment failure must not fail the feed.
    try {
      const tickers = await resolveSecTickers(result.filings.map((f) => f.cik));
      result.filings = result.filings.map((filing) => ({
        ...filing,
        ticker: filing.cik ? tickers[filing.cik] ?? null : null,
      }));
    } catch (error) {
      console.warn("[api/economics/filings] ticker enrichment skipped:", error);
    }
    await writeLastGood(cacheName, result);
    return NextResponse.json(result);
  } catch (error) {
    console.error("[api/economics/filings] error:", error);
    const last = await readLastGood<FilingsFeedResult>(cacheName);
    if (last?.data?.filings?.length) {
      return NextResponse.json({
        ...last.data,
        cached: true,
        stale: true,
        retrievedAt: last.savedAt,
      });
    }
    return NextResponse.json(
      { filings: [], form, error: "The SEC filings feed is unavailable right now." },
      { status: 502 },
    );
  }
}
