import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

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

// POST /api/symbols — user-added symbol for a market.
// Body: { market: "US", symbol: "TSLA" } (symbols: comma list also accepted)
// Verifies the ticker resolves on Yahoo, adds it to JDDS (upsert — re-adding
// just refreshes the price), prices it immediately, and returns the result.
export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const rawMarket: string = (body.market || "US").toUpperCase();
    const market: string = MARKET_ID_MAP[rawMarket] || rawMarket;

    const rawSymbols = (Array.isArray(body.symbols) ? body.symbols : [body.symbol])
      .map((s: unknown) => String(s).trim().toUpperCase())
      .filter(Boolean);
    if (rawSymbols.length === 0) {
      return NextResponse.json({ error: "Enter a symbol" }, { status: 400 });
    }

    const results = await fetchYahooBatchQuote(rawSymbols, market);
    const added: { symbol: string; name: string; price: number; changePct: number }[] = [];
    const failed: string[] = [];

    for (let i = 0; i < rawSymbols.length; i++) {
      const symbol = rawSymbols[i];
      const res = results[i];
      if (res.status !== "ok" || !res.quote) {
        failed.push(symbol);
        continue;
      }

      const asset = await prisma.asset.upsert({
        where: { marketId_symbol: { marketId: market, symbol } },
        update: { isActive: true },
        create: {
          symbol,
          name: symbol, // name filled in on the next full refresh pass
          marketId: market,
          isActive: true,
        },
      });

      await prisma.price.upsert({
        where: { assetId: asset.id },
        update: {
          price: res.quote.price,
          changePct: res.quote.changePct,
          volume: res.quote.volume ?? undefined,
          source: "yfinance",
        },
        create: {
          assetId: asset.id,
          price: res.quote.price,
          changePct: res.quote.changePct,
          volume: res.quote.volume ?? undefined,
          source: "yfinance",
        },
      });

      added.push({ symbol, name: asset.name, price: res.quote.price, changePct: res.quote.changePct });
    }

    return NextResponse.json({
      success: true,
      market,
      added,
      failed,
      total: added.length,
    });
  } catch (err) {
    console.error("[api/symbols] Error:", err);
    return NextResponse.json({ error: "Failed to add symbol" }, { status: 500 });
  }
}

// DELETE /api/symbols — remove a user-added symbol from a market.
// Body: { market: "US", symbol: "BRK.B" }
export async function DELETE(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const rawMarket: string = (body.market || "US").toUpperCase();
    const market: string = MARKET_ID_MAP[rawMarket] || rawMarket;
    const symbol = String(body.symbol || "").trim().toUpperCase();
    if (!symbol) {
      return NextResponse.json({ error: "Missing symbol" }, { status: 400 });
    }

    await prisma.asset.deleteMany({ where: { marketId: market, symbol } });
    return NextResponse.json({ success: true, removed: symbol });
  } catch (err) {
    console.error("[api/symbols] DELETE Error:", err);
    return NextResponse.json({ error: "Failed to remove symbol" }, { status: 500 });
  }
}
