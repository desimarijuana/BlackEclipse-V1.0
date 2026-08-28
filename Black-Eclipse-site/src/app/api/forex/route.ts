import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

// Major forex pairs (Yahoo symbols). The bridge is called with market "US" so
// no suffix is appended — "EURUSD=X" style symbols pass through untouched.
const FOREX_PAIRS: Array<{ symbol: string; name: string; base: string; quote: string }> = [
  { symbol: "EURUSD=X", name: "Euro / US Dollar", base: "EUR", quote: "USD" },
  { symbol: "GBPUSD=X", name: "British Pound / US Dollar", base: "GBP", quote: "USD" },
  { symbol: "USDJPY=X", name: "US Dollar / Japanese Yen", base: "USD", quote: "JPY" },
  { symbol: "USDCHF=X", name: "US Dollar / Swiss Franc", base: "USD", quote: "CHF" },
  { symbol: "AUDUSD=X", name: "Australian Dollar / US Dollar", base: "AUD", quote: "USD" },
  { symbol: "USDCAD=X", name: "US Dollar / Canadian Dollar", base: "USD", quote: "CAD" },
  { symbol: "NZDUSD=X", name: "New Zealand Dollar / US Dollar", base: "NZD", quote: "USD" },
  { symbol: "USDCNY=X", name: "US Dollar / Chinese Yuan", base: "USD", quote: "CNY" },
  { symbol: "USDINR=X", name: "US Dollar / Indian Rupee", base: "USD", quote: "INR" },
  { symbol: "USDPKR=X", name: "US Dollar / Pakistani Rupee", base: "USD", quote: "PKR" },
  { symbol: "USDTRY=X", name: "US Dollar / Turkish Lira", base: "USD", quote: "TRY" },
  { symbol: "USDBRL=X", name: "US Dollar / Brazilian Real", base: "USD", quote: "BRL" },
  { symbol: "USDMXN=X", name: "US Dollar / Mexican Peso", base: "USD", quote: "MXN" },
  { symbol: "USDZAR=X", name: "US Dollar / South African Rand", base: "USD", quote: "ZAR" },
  { symbol: "USDSGD=X", name: "US Dollar / Singapore Dollar", base: "USD", quote: "SGD" },
  { symbol: "USDHKD=X", name: "US Dollar / Hong Kong Dollar", base: "USD", quote: "HKD" },
  { symbol: "USDKRW=X", name: "US Dollar / South Korean Won", base: "USD", quote: "KRW" },
  { symbol: "USDTHB=X", name: "US Dollar / Thai Baht", base: "USD", quote: "THB" },
  { symbol: "USDIDR=X", name: "US Dollar / Indonesian Rupiah", base: "USD", quote: "IDR" },
  { symbol: "USDVND=X", name: "US Dollar / Vietnamese Dong", base: "USD", quote: "VND" },
  { symbol: "USDAED=X", name: "US Dollar / UAE Dirham", base: "USD", quote: "AED" },
  { symbol: "USDSAR=X", name: "US Dollar / Saudi Riyal", base: "USD", quote: "SAR" },
  { symbol: "USDEGP=X", name: "US Dollar / Egyptian Pound", base: "USD", quote: "EGP" },
  { symbol: "USDNGN=X", name: "US Dollar / Nigerian Naira", base: "USD", quote: "NGN" },
  { symbol: "USDRUB=X", name: "US Dollar / Russian Ruble", base: "USD", quote: "RUB" },
  { symbol: "USDPLN=X", name: "US Dollar / Polish Zloty", base: "USD", quote: "PLN" },
  { symbol: "USDSEK=X", name: "US Dollar / Swedish Krona", base: "USD", quote: "SEK" },
  { symbol: "USDNOK=X", name: "US Dollar / Norwegian Krone", base: "USD", quote: "NOK" },
  { symbol: "USDDKK=X", name: "US Dollar / Danish Krone", base: "USD", quote: "DKK" },
  { symbol: "USDHUF=X", name: "US Dollar / Hungarian Forint", base: "USD", quote: "HUF" },
  { symbol: "USDCZK=X", name: "US Dollar / Czech Koruna", base: "USD", quote: "CZK" },
  { symbol: "USDILS=X", name: "US Dollar / Israeli Shekel", base: "USD", quote: "ILS" },
  { symbol: "USDPHP=X", name: "US Dollar / Philippine Peso", base: "USD", quote: "PHP" },
  { symbol: "USDMYR=X", name: "US Dollar / Malaysian Ringgit", base: "USD", quote: "MYR" },
];

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
