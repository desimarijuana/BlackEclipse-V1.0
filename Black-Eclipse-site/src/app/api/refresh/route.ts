import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

// The yfinance bridge batches all symbols over ONE shared Python session
// (fast_info, chart endpoint only) — no per-symbol HTTP round-trips, no
// Yahoo 404/429 bursts on full-page refreshes.

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

// POST /api/refresh — fetch live yfinance prices for a market's assets and
// write them into JDDS. Body: { market: "US" | "PK" | "CRYPTO" | ..., symbols?: string[] }
// When `symbols` is provided, only those symbols are refreshed (e.g. the page
// currently shown in the screener). Otherwise the market's full universe is.
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
      // Pull the market's active assets. When no explicit symbols are given,
      // refresh the ENTIRE universe (no cap) — small markets now hold 30-200
      // assets and users expect every row on the page to get priced.
      const assets = await prisma.asset.findMany({
        where: {
          marketId: market,
          isActive: true,
          ...(symbols.length > 0 ? { symbol: { in: symbols } } : {}),
        },
        select: { id: true, symbol: true },
      });

      let ok = 0;
      let failed = 0;

      // Batched bridge calls (chunked for big universes) — the bridge keeps one
      // shared session and a small thread pool per call, then we persist each hit.
      const CHUNK = 200;
      for (let i = 0; i < assets.length; i += CHUNK) {
        const chunk = assets.slice(i, i + CHUNK);
        const chunkResults = await fetchYahooBatchQuote(
          chunk.map((a) => a.symbol),
          market
        );
        for (let j = 0; j < chunkResults.length; j++) {
          const result = chunkResults[j];
          if (result.status !== "ok" || !result.quote) {
            failed++;
            continue;
          }
          const asset = chunk[j];
          if (!asset) continue;

          // Only persist columns that exist on the Price model. (Day high/low,
          // open, previous close, 52w range are NOT stored in JDDS. The v7
          // fundamentals endpoint is 401-blocked by Yahoo, so we rely on the
          // price + volume the chart endpoint already returns and leave the
          // fundamental fields untouched.)
          const data = {
            price: result.quote.price,
            changePct: result.quote.changePct,
            volume: result.quote.volume ?? undefined,
            source: "yfinance",
          };

          await prisma.price.upsert({
            where: { assetId: asset.id },
            update: data,
            create: { assetId: asset.id, ...data },
          });
          ok++;
        }
      }

      return NextResponse.json({ success: true, total: assets.length, ok, failed });
    } finally {
      refreshInFlight.delete(market);
    }
  } catch (err) {
    console.error("[api/refresh] Error:", err);
    return NextResponse.json({ error: "Failed to refresh prices" }, { status: 500 });
  }
}
