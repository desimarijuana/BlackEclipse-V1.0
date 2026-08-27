import { NextResponse } from "next/server";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

// Major commodities (Yahoo futures symbols). The bridge is called with market
// "US" so no suffix is appended — "GC=F" style symbols pass through untouched.
const COMMODITIES: Array<{ symbol: string; name: string; unit: string }> = [
  { symbol: "GC=F", name: "Gold", unit: "USD/oz" },
  { symbol: "SI=F", name: "Silver", unit: "USD/oz" },
  { symbol: "CL=F", name: "Crude Oil (WTI)", unit: "USD/bbl" },
  { symbol: "BZ=F", name: "Brent Crude", unit: "USD/bbl" },
  { symbol: "NG=F", name: "Natural Gas", unit: "USD/MMBtu" },
  { symbol: "HG=F", name: "Copper", unit: "USD/lb" },
  { symbol: "PL=F", name: "Platinum", unit: "USD/oz" },
  { symbol: "PA=F", name: "Palladium", unit: "USD/oz" },
  { symbol: "ALI=F", name: "Aluminum", unit: "USD/t" },
  { symbol: "ZW=F", name: "Wheat", unit: "USc/bu" },
  { symbol: "ZC=F", name: "Corn", unit: "USc/bu" },
  { symbol: "ZS=F", name: "Soybeans", unit: "USc/bu" },
  { symbol: "KC=F", name: "Coffee", unit: "USc/lb" },
  { symbol: "CC=F", name: "Cocoa", unit: "USD/t" },
  { symbol: "SB=F", name: "Sugar", unit: "USc/lb" },
  { symbol: "CT=F", name: "Cotton", unit: "USc/lb" },
  { symbol: "LE=F", name: "Live Cattle", unit: "USc/lb" },
];

// In-memory SWR cache — commodity quotes move slowly and the bridge call is
// expensive, so serve cached instantly and refresh in the background.
const CACHE_TTL_MS = 2 * 60 * 1000;
let cache: { t: number; data: unknown } | null = null;
let rebuildInFlight = false;

async function buildCommodities() {
  const results = await fetchYahooBatchQuote(
    COMMODITIES.map((c) => c.symbol),
    "US"
  );
  const commodities = COMMODITIES.map((c, i) => {
    const r = results[i];
    const ok = r?.status === "ok" && r.quote && r.quote.price > 0;
    return {
      symbol: c.symbol,
      name: c.name,
      unit: c.unit,
      price: ok ? r.quote!.price : 0,
      changePct: ok ? r.quote!.changePct : 0,
      found: !!ok,
    };
  });
  return { commodities, source: commodities.some((c) => c.found) ? "yfinance" : "cache" };
}

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildCommodities()
    .then((data) => {
      // Only cache a build that actually resolved at least one quote; a
      // transient failure (bridge timeout during cold compile) must not
      // pin an all-empty payload for the next few minutes.
      const anyFound = Array.isArray(data.commodities) && data.commodities.some((c) => c.found);
      if (anyFound) cache = { t: Date.now(), data };
    })
    .catch((err) => console.error("[api/commodities] background rebuild error:", err))
    .finally(() => { rebuildInFlight = false; });
}

// GET /api/commodities — live major commodity futures quotes.
export async function GET() {
  try {
    if (cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) {
        return NextResponse.json(cache.data);
      }
      startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    const data = await buildCommodities();
    const anyFound = Array.isArray(data.commodities) && data.commodities.some((c) => c.found);
    if (anyFound) cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/commodities] GET error:", err);
    return NextResponse.json({ commodities: [], source: "error" }, { status: 500 });
  }
}
