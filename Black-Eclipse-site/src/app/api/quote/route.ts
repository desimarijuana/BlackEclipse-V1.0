import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";

export const dynamic = "force-dynamic";

type SuggestionRow = {
  symbol: string;
  name: string;
  marketId: string;
  currency: string;
  price: number;
  /** True when the row came from the IndexQuote table (market index). */
  isIndex: boolean;
};

// Live symbol search straight from the JDDS database so users can only pin
// symbols that actually exist (with their real market + price). Uses raw SQL
// because SQLite LIKE is case-insensitive while Prisma `contains` is not.
//
// Also unions in market indices from the IndexQuote table (S&P 500, Nifty 50,
// FTSE 100, …) so the chart autocomplete can find them — indices live in a
// separate table and are NEVER assets, so they were previously unsearchable.
async function searchSymbols(q: string): Promise<SuggestionRow[]> {
  const like = `%${q}%`;
  const exact = q;
  const prefix = `${q}%`;
  const [assetRows, indexRows] = await Promise.all([
    prisma.$queryRaw<
      Array<{ symbol: string; name: string; marketId: string; price: number }>
    >`
      SELECT a."symbol" AS symbol, a."name" AS name, a."marketId" AS marketId, p."price" AS price
      FROM "Asset" a
      JOIN "Price" p ON p."assetId" = a."id"
      WHERE a."isActive" = 1 AND (a."symbol" LIKE ${like} OR a."name" LIKE ${like})
      ORDER BY
        CASE WHEN UPPER(a."symbol") = ${exact} THEN 0 ELSE 1 END,
        CASE WHEN UPPER(a."symbol") LIKE ${prefix} THEN 0 ELSE 1 END,
        p."marketCap" IS NULL,
        p."marketCap" DESC
      LIMIT 8
    `,
    prisma.$queryRaw<
      Array<{ symbol: string; name: string; marketId: string; price: number }>
    >`
      SELECT "symbol" AS symbol, "name" AS name, "marketId" AS marketId, "price" AS price
      FROM "IndexQuote"
      WHERE "price" > 0 AND ("symbol" LIKE ${like} OR "name" LIKE ${like})
      LIMIT 6
    `,
  ]);

  const merged: SuggestionRow[] = [
    ...assetRows.map((r) => ({
      symbol: r.symbol,
      name: r.name,
      marketId: r.marketId,
      currency: MARKET_CURRENCY[r.marketId] || "$",
      price: r.price,
      isIndex: false,
    })),
    ...indexRows.map((r) => ({
      symbol: r.symbol,
      name: r.name,
      marketId: r.marketId,
      currency: MARKET_CURRENCY[r.marketId] || "$",
      price: r.price,
      isIndex: true,
    })),
  ];

  // Rank: exact symbol → symbol prefix → index name matches → everything else.
  // Index name matches deliberately outrank asset name matches so "Nasdaq" /
  // "FTSE 100" surface the benchmark above the many ETFs that also match.
  const rank = (r: SuggestionRow) => {
    const sym = r.symbol.toUpperCase();
    if (sym === exact) return 0;
    if (sym.startsWith(q)) return 1;
    if (r.isIndex) return 2;
    return 3;
  };
  const seen = new Set<string>();
  return merged
    .sort((a, b) => rank(a) - rank(b))
    .filter((r) => {
      const key = r.symbol.toUpperCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 8);
}

// GET /api/quote?symbols=OGDC,AAPL,BTC — resolve arbitrary pinned symbols
// across ALL markets in JDDS (name, live price, currency, freshness).
//   ?market=PK  — optional: only resolve symbols within one market, removing
//                 ambiguity when the same symbol exists in several markets.
// GET /api/quote?q=ogd — database symbol search for the pin-input autocomplete.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);

  // --- Autocomplete path ---
  const q = (searchParams.get("q") || "").trim().toUpperCase();
  if (q.length >= 1) {
    try {
      const suggestions = await searchSymbols(q.slice(0, 30));
      return NextResponse.json({ suggestions });
    } catch (err) {
      console.error("[api/quote] search error:", err);
      return NextResponse.json({ suggestions: [] }, { status: 500 });
    }
  }

  // --- Resolve pinned symbols path ---
  const raw = searchParams.get("symbols") || "";
  const marketScope = (searchParams.get("market") || "").trim().toUpperCase() || null;
  // JDDS stores bare symbols (RELIANCE, not RELIANCE.NS) — strip exchange
  // suffixes so user-typed variants like "AAPL.US" or "OGDC.PSX" resolve.
  const symbols = [
    ...new Set(
      raw
        .split(",")
        .map((s) => s.trim().toUpperCase().replace(/\.(PSX|NS|BO|SS|SZ|BJ|TW|T|HK|KS|KQ|SI|KL|AX|L|DE|PA|AS|TO|SA|AE|JO|CA|NG|ME|IS|JK|BK|VN|US)$/, ""))
        .filter(Boolean)
    ),
  ].slice(0, 20);

  if (symbols.length === 0) {
    return NextResponse.json({ quotes: [] });
  }

  try {
    const rows = await prisma.asset.findMany({
      where: {
        symbol: { in: symbols },
        isActive: true,
        ...(marketScope ? { marketId: marketScope } : {}),
      },
      select: {
        symbol: true,
        name: true,
        marketId: true,
        price: { select: { price: true, changePct: true, source: true, updatedAt: true } },
      },
    });

    // Deterministic winner per symbol: prefer priced rows; among those,
    // prefer US listings as the tiebreak for cross-market symbols (AAPL
    // exists once, but generic tickers collide across exchanges). Without
    // ?market= this is documented "best effort" resolution.
    const bySymbol = new Map<string, (typeof rows)[number]>();
    const rank = (r: (typeof rows)[number]) => (r.price && r.price.price > 0 ? (r.marketId === "US" ? 2 : 1) : 0);
    for (const r of rows) {
      const key = r.symbol.toUpperCase();
      const prev = bySymbol.get(key);
      if (!prev || rank(r) > rank(prev)) bySymbol.set(key, r);
    }

    const quotes = symbols.map((sym) => {
      const r = bySymbol.get(sym);
      if (!r || !r.price || r.price.price <= 0) {
        return { symbol: sym, name: sym, price: 0, changePercent: 0, currency: "$", found: false };
      }
      return {
        symbol: sym,
        name: r.name,
        price: r.price.price,
        changePercent: r.price.changePct,
        currency: MARKET_CURRENCY[r.marketId] || "$",
        marketId: r.marketId,
        source: r.price.source,
        updatedAt: r.price.updatedAt,
        found: true,
      };
    });

    return NextResponse.json({ quotes });
  } catch (err) {
    console.error("[api/quote] Error:", err);
    return NextResponse.json({ quotes: [] }, { status: 500 });
  }
}
