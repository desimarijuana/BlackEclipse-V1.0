import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { searchIndices, resolveIndex } from "@/lib/indices";
import { fetchPsxIndexQuote } from "@/lib/scraper/fetchers/psx-index";

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
// Three sources are unioned, because an instrument can live in any of them:
//   1. `Asset` — the JDDS universe (equities, crypto, ETFs, …).
//   2. `IndexQuote` — index levels already fetched into JDDS.
//   3. The index REGISTRY (`@/lib/indices`) — indices a provider can chart even
//      before they have an IndexQuote row (e.g. the PSX benchmarks), so the
//      autocomplete can always find "Nifty 50" or "KSE 100".
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
    // Registry indices not already present from IndexQuote. These carry the
    // canonical chart symbol, so picking one charts the right instrument.
    ...searchIndices(q).map((def) => ({
      symbol: def.symbol,
      name: def.name,
      marketId: def.market,
      currency: def.currency,
      price: 0,
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
  // Keep the ORIGINAL symbols: exchange-suffix stripping would corrupt dot-carrying
  // index tickers (000001.SS → 000001, which is a different instrument). The
  // stripped variant is computed per-symbol only for the Asset lookup below.
  const symbols = [
    ...new Set(
      raw
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean)
    ),
  ].slice(0, 20);

  if (symbols.length === 0) {
    return NextResponse.json({ quotes: [] });
  }

  // JDDS stores bare symbols (RELIANCE, not RELIANCE.NS) — strip exchange
  // suffixes so user-typed variants like "AAPL.US" or "OGDC.PSX" resolve.
  const assetKey = (s: string) =>
    s.replace(/\.(PSX|NS|BO|SS|SZ|BJ|TW|T|HK|KS|KQ|SI|KL|AX|L|DE|PA|AS|TO|SA|AE|JO|CA|NG|ME|IS|JK|BK|VN|US)$/, "");

  try {
    const looksLikeIndex = (s: string) => Boolean(resolveIndex(s)) || s.startsWith("^");
    const indexSymbols = symbols.filter(looksLikeIndex);
    const assetSymbols = symbols.filter((s) => !looksLikeIndex(s));

    const [rows, indexRows] = await Promise.all([
      assetSymbols.length
        ? prisma.asset.findMany({
            where: {
              symbol: { in: assetSymbols.map(assetKey) },
              isActive: true,
              ...(marketScope ? { marketId: marketScope } : {}),
            },
            select: {
              symbol: true,
              name: true,
              marketId: true,
              price: { select: { price: true, changePct: true, source: true, updatedAt: true } },
            },
          })
        : Promise.resolve([]),
      // Indices live in IndexQuote, keyed by their CANONICAL ticker and by any
      // alias a caller may pass (`SPX`, `DJI`, `KSE100`). Look up both so a
      // legacy alias still resolves to the stored index row.
      indexSymbols.length
        ? prisma.indexQuote.findMany({
            where: {
              symbol: {
                in: indexSymbols.flatMap((s) => {
                  const def = resolveIndex(s);
                  return def ? [def.symbol, ...def.aliases.map(a => a.toUpperCase())] : [s];
                }),
              },
            },
            select: { symbol: true, name: true, marketId: true, price: true, changePct: true, updatedAt: true },
          })
        : Promise.resolve([]),
    ]);

    // The IndexQuote row for a requested alias may be stored under the canonical
    // ticker — map every requested symbol to whichever row matched.
    const indexByCanonical = new Map<string, (typeof indexRows)[number]>();
    for (const r of indexRows) indexByCanonical.set(r.symbol.toUpperCase(), r);
    const findIndex = (s: string) => {
      const def = resolveIndex(s);
      const candidates = def
        ? [def.symbol.toUpperCase(), ...def.aliases.map(a => a.toUpperCase()), s]
        : [s];
      for (const c of candidates) {
        const row = indexByCanonical.get(c);
        if (row) return row;
      }
      return undefined;
    };

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

    // PSX benchmarks have no IndexQuote row (Yahoo dropped them), so ask the
    // exchange directly for their latest level rather than reporting "not found".
    const psxSymbols = indexSymbols.filter((s) => resolveIndex(s)?.provider === "psx");
    const psxQuotes = new Map<string, { price: number; changePct: number }>();
    await Promise.all(
      psxSymbols.map(async (s) => {
        const q = await fetchPsxIndexQuote(s);
        if (q) psxQuotes.set(s, { price: q.price, changePct: q.changePct });
      })
    );

    const quotes = symbols.map((sym) => {
      // Indices first — they are not Asset rows, so the asset map can never
      // resolve them. Report the requested `sym` back so the caller's key matches.
      if (looksLikeIndex(sym)) {
        const idx = findIndex(sym);
        const def = resolveIndex(sym);
        const currency = def?.currency || (idx ? MARKET_CURRENCY[idx.marketId] : undefined) || "$";
        // Prefer the stored IndexQuote row; fall back to the live PSX quote.
        const psx = psxQuotes.get(sym) ?? (def?.provider === "psx" ? psxQuotes.get(def.symbol) : undefined);
        const price = idx && idx.price > 0 ? idx.price : psx?.price ?? 0;
        if (price > 0) {
          return {
            symbol: sym,
            name: idx?.name ?? def?.name ?? sym,
            price,
            changePercent: idx && idx.price > 0 ? idx.changePct : psx?.changePct ?? 0,
            currency,
            marketId: idx?.marketId ?? def?.market,
            source: idx && idx.price > 0 ? "index" : "psx",
            updatedAt: idx?.updatedAt,
            found: true,
          };
        }
        return {
          symbol: sym,
          name: def?.name ?? sym,
          price: 0,
          changePercent: 0,
          currency,
          marketId: def?.market,
          found: false,
        };
      }

      const r = bySymbol.get(assetKey(sym));
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
