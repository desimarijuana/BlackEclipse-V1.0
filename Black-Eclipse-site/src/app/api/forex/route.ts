import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";
import { FOREX_CATALOG as FOREX_PAIRS } from "@/lib/market-catalog";

export const dynamic = "force-dynamic";


// In-memory SWR cache — forex quotes move slowly and the bridge call is
// expensive, so serve cached instantly and refresh in the background.
const CACHE_TTL_MS = 2 * 60 * 1000;
let cache: { t: number; data: unknown } | null = null;
let rebuildInFlight = false;

// Persisted copy of the last good payload (SystemConfig key). Survives server
// restarts so a cold start serves instantly instead of blocking 7-8s on the
// Python bridge while the user stares at "loading forex…".
const PERSIST_KEY = "api_cache:forex";

async function loadPersisted(): Promise<unknown | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: PERSIST_KEY } });
    if (!row?.value) return null;
    const parsed = JSON.parse(row.value);
    if (parsed && Array.isArray(parsed.pairs) && parsed.pairs.some((p: { found: boolean }) => p.found)) {
      return parsed;
    }
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

async function buildForex() {
  const results = await fetchYahooBatchQuote(
    FOREX_PAIRS.map((p) => p.symbol),
    "US"
  );
  const pairs = FOREX_PAIRS.map((p, i) => {
    const r = results[i];
    const ok = r?.status === "ok" && r.quote && r.quote.price > 0;
    return {
      symbol: p.symbol,
      name: p.name,
      base: p.base,
      quote: p.quote,
      price: ok ? r.quote!.price : 0,
      changePct: ok ? r.quote!.changePct : 0,
      found: !!ok,
    };
  });
  return { pairs, source: pairs.some((p) => p.found) ? "yfinance" : "cache" };
}

async function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  try {
    const data = await buildForex();
    const anyFound = data.pairs.some((p) => p.found);
    if (anyFound) {
      cache = { t: Date.now(), data };
      await persist(data);
    }
  } catch (err) {
    console.error("[api/forex] background rebuild error:", err);
  } finally {
    rebuildInFlight = false;
  }
}

// GET /api/forex — live major forex pair quotes.
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
    const data = await buildForex();
    cache = { t: Date.now(), data };
    await persist(data);
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/forex] GET error:", err);
    return NextResponse.json({ pairs: [], source: "error" }, { status: 500 });
  }
}
