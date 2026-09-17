import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";
import { COMMODITY_CATALOG as COMMODITIES } from "@/lib/market-catalog";

export const dynamic = "force-dynamic";


// In-memory SWR cache — commodity quotes move slowly and the bridge call is
// expensive, so serve cached instantly and refresh in the background.
const CACHE_TTL_MS = 2 * 60 * 1000;
let cache: { t: number; data: unknown } | null = null;
let rebuildInFlight = false;

// Persisted copy of the last good payload (SystemConfig key). Survives server
// restarts so a cold start serves instantly instead of blocking 7-8s on the
// Python bridge while the user stares at "loading commodities…".
const PERSIST_KEY = "api_cache:commodities";

function isGoodPayload(data: unknown): boolean {
  return Array.isArray((data as { commodities?: { found: boolean }[] }).commodities)
    && (data as { commodities: { found: boolean }[] }).commodities.some((c) => c.found);
}

async function loadPersisted(): Promise<unknown | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: PERSIST_KEY } });
    if (!row?.value) return null;
    const parsed = JSON.parse(row.value);
    if (isGoodPayload(parsed)) return parsed;
  } catch { /* ignore — fall through to a live build */ }
  return null;
}

async function persist(data: unknown) {
  try {
    await prisma.systemConfig.upsert({
      where: { key: PERSIST_KEY },
      update: { value: JSON.stringify(data) },
      create: { key: PERSIST_KEY, value: JSON.stringify(data) },
    });
  } catch { /* ignore — persistence is best-effort */ }
}

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

async function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  try {
    const data = await buildCommodities();
    // Only cache/persist a build that actually resolved at least one quote; a
    // transient failure (bridge timeout during cold compile) must not
    // pin an all-empty payload for the next few minutes.
    if (isGoodPayload(data)) {
      cache = { t: Date.now(), data };
      await persist(data);
    }
  } catch (err) {
    console.error("[api/commodities] background rebuild error:", err);
  } finally {
    rebuildInFlight = false;
  }
}

// GET /api/commodities — live major commodity futures quotes.
export async function GET() {
  try {
    if (cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) {
        return NextResponse.json(cache.data);
      }
      void startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    // Cold start (no in-memory cache): serve the persisted payload instantly
    // when one exists and refresh in the background.
    const persisted = await loadPersisted();
    if (persisted) {
      cache = { t: Date.now(), data: persisted };
      void startBackgroundRebuild();
      return NextResponse.json(persisted);
    }
    const data = await buildCommodities();
    if (isGoodPayload(data)) {
      cache = { t: Date.now(), data };
      await persist(data);
    }
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/commodities] GET error:", err);
    return NextResponse.json({ commodities: [], source: "error" }, { status: 500 });
  }
}
