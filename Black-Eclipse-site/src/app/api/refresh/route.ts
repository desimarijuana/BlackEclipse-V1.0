import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooQuote } from "@/lib/yfinance";

export const dynamic = "force-dynamic";

// Yahoo aggressively rate-limits concurrent requests (404/429 when a burst of
// chart calls fires at once). We bound concurrency and insert a small delay
// between requests so a full-page refresh stays under the throttle and returns
// live prices instead of 404s.
const CONCURRENCY = 3;
const BETWEEN_DELAY_MS = 250;
const MAX_RETRIES = 2;

// Map UI country codes to JDDS market ids (mirrors /api/stocks).
const MARKET_ID_MAP: Record<string, string> = {
  US: "US",
  USA: "US",
  PK: "PK",
  IN: "IN",
  CRYPTO: "CRYPTO",
  China: "CN",
  CN: "CN",
  Taiwan: "TW",
  TW: "TW",
  HK: "HK",
  JP: "JP",
  KR: "KR",
  SG: "SG",
  MY: "MY",
  AU: "AU",
  UK: "UK",
  DE: "DE",
  FR: "FR",
  NL: "NL",
  CA: "CA",
  BR: "BR",
  MX: "MX",
  SA: "SA",
  AE: "AE",
  ZA: "ZA",
  EG: "EG",
  NG: "NG",
  RU: "RU",
  TR: "TR",
  ID: "ID",
  TH: "TH",
  VN: "VN",
};

// Guards against concurrent refreshes for the same market.
const refreshInFlight = new Set<string>();

// How many assets to refresh per request (bounded to keep the response fast).
const MAX_REFRESH = 50;

// POST /api/refresh — fetch live yfinance prices for a market's assets and
// write them into JDDS. Body: { market: "US" | "PK" | "CRYPTO" | ..., symbols?: string[] }
// When `symbols` is provided, only those symbols are refreshed (e.g. the page
// currently shown in the screener). Otherwise the first MAX_REFRESH assets are.
export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const rawMarket: string = (body.market || "US").toUpperCase();
    const market: string = MARKET_ID_MAP[rawMarket] || rawMarket;
    const symbols: string[] = Array.isArray(body.symbols) ? body.symbols : [];

    if (refreshInFlight.has(market)) {
      return NextResponse.json({ success: true, total: 0, ok: 0, failed: 0, skipped: true });
    }
    refreshInFlight.add(market);

    try {
      // Pull the market's active assets (bounded). If symbols given, match them.
      const assets = await prisma.asset.findMany({
        where: {
          marketId: market,
          isActive: true,
          ...(symbols.length > 0 ? { symbol: { in: symbols } } : {}),
        },
        take: symbols.length > 0 ? symbols.length : MAX_REFRESH,
        select: { id: true, symbol: true },
      });

      let ok = 0;
      let failed = 0;

      // Sequential worker pool with a small delay between requests keeps us
      // under Yahoo's rate limit. The v7 fundamentals endpoint (market cap,
      // P/E, dividend) is now permanently 401-blocked by Yahoo, so we rely on
      // the price + volume the chart endpoint already returns and leave the
      // fundamental fields untouched (they stay whatever the last scrape wrote).
      let cursor = 0;
      const worker = async () => {
        while (cursor < assets.length) {
          const idx = cursor++;
          const asset = assets[idx];
          let quote: Awaited<ReturnType<typeof fetchYahooQuote>> = null;
          for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            quote = await fetchYahooQuote(asset.symbol, market);
            if (quote) break;
            if (attempt < MAX_RETRIES) await new Promise((r) => setTimeout(r, 800));
          }
          if (!quote) {
            failed++;
            continue;
          }

          // Only persist columns that exist on the Price model. (Day high/low,
          // open, previous close, 52w range are NOT stored in JDDS.)
          const data = {
            price: quote.price,
            changePct: quote.changePct,
            volume: quote.volume ?? undefined,
            source: "yfinance",
          };

          await prisma.price.upsert({
            where: { assetId: asset.id },
            update: data,
            create: { assetId: asset.id, ...data },
          });
          ok++;
          await new Promise((r) => setTimeout(r, BETWEEN_DELAY_MS));
        }
      };

      await Promise.all(Array.from({ length: Math.max(1, Math.min(CONCURRENCY, assets.length)) }, worker));

      return NextResponse.json({ success: true, total: assets.length, ok, failed });
    } finally {
      refreshInFlight.delete(market);
    }
  } catch (err) {
    console.error("[api/refresh] Error:", err);
    return NextResponse.json({ error: "Failed to refresh prices" }, { status: 500 });
  }
}
