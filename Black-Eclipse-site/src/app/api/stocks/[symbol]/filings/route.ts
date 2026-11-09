import { NextResponse } from "next/server";
import { fetchCapability } from "@/lib/harness/data-bridge";
import { rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// GET /api/stocks/[symbol]/filings?market=US&form=10-K&date_from=2024-01-01&date_to=2025-12-31
//
// Native read-only route over the SEC filing-LIST capability. SEC EDGAR's
// submissions index is the authority; a ticker outside it is `not_found`, a
// non-US market is `not_covered`. The route never constructs a document URL
// that the SEC did not publish.

const CACHE_TTL_MS = 30 * 60 * 1000;
const cache = new Map<string, { at: number; payload: Record<string, unknown> }>();
const inFlight = new Map<string, Promise<Record<string, unknown>>>();

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const FORM_RE = /^[A-Za-z0-9/-]{1,12}$/;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol: rawSymbol } = await params;
  const symbol = rawSymbol.trim().toUpperCase();
  if (!symbol) {
    return NextResponse.json({ status: "UNAVAILABLE", error: "A symbol is required." }, { status: 400 });
  }

  const url = new URL(request.url);
  const market = (url.searchParams.get("market") ?? "US").trim().toUpperCase();
  const form = (url.searchParams.get("form") ?? "").trim().toUpperCase();
  const dateFrom = (url.searchParams.get("date_from") ?? "").trim();
  const dateTo = (url.searchParams.get("date_to") ?? "").trim();

  if (form && !FORM_RE.test(form)) {
    return NextResponse.json({ status: "UNAVAILABLE", error: "form is not a plausible SEC form type." }, { status: 400 });
  }
  for (const [label, value] of [["date_from", dateFrom], ["date_to", dateTo]] as const) {
    if (value && !DATE_RE.test(value)) {
      return NextResponse.json({ status: "UNAVAILABLE", error: `${label} must be YYYY-MM-DD.` }, { status: 400 });
    }
  }

  const rl = rateLimit(`stock-filings:${clientKey(request)}`, { limit: 30, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "Too many filing requests — slow down." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSec) } },
    );
  }

  const key = `${symbol}|${market}|${form}|${dateFrom}|${dateTo}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
    return NextResponse.json({ ...hit.payload, cached: true });
  }

  try {
    let pending = inFlight.get(key);
    if (!pending) {
      pending = fetchCapability("sec_filing_list", {
        symbol,
        market,
        ...(form ? { form } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }) as Promise<Record<string, unknown>>;
      inFlight.set(key, pending);
      void pending.finally(() => inFlight.delete(key));
    }
    const payload = await pending;
    cache.set(key, { at: Date.now(), payload });
    return NextResponse.json({ ...payload, cached: false });
  } catch (error) {
    console.error("[api/stocks/filings] error:", error);
    return NextResponse.json(
      { status: "UNAVAILABLE", code: "FILINGS_ROUTE_ERROR", error: "Filing lookup failed." },
      { status: 500 },
    );
  }
}
