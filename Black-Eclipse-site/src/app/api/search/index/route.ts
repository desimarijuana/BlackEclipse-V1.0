// ── GET /api/search/index ──────────────────────────────────────────────────
// Streams a compact, versioned snapshot of the JDDS universe for the client
// search index. The client caches this by version and rebuilds an in-memory
// FlexSearch index once — so per-keystroke search never touches the network or
// SQLite again. Static registries (pages/indicators/actions) are bundled in
// the client already; only the volatile asset universe is fetched here.

import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// Bump whenever the wire format changes so stale caches are invalidated.
const INDEX_VERSION = "2.0.0";

// Derive a coarse asset class from market + security type so the client can
// render a category icon without a lookup.
function assetClassOf(marketId: string, securityType: string | null): string {
  if (marketId === "CRYPTO") return "crypto";
  const t = (securityType || "").toLowerCase();
  if (t.includes("etf")) return "etf";
  if (t.includes("mutual")) return "etf";
  if (t.includes("adr")) return "equity";
  if (t.includes("preferred")) return "equity";
  if (t.includes("warrant")) return "equity";
  return "equity";
}

// Cap the shipped universe so the payload stays bounded even if the DB grows
// far beyond the current ~55k assets. Sorted by marketCap desc so the biggest,
// most-searched names are always included within the cap.
const MAX_ASSETS = 120_000;

export async function GET() {
  try {
    const rows = await prisma.asset.findMany({
      where: { isActive: true },
      select: {
        symbol: true,
        name: true,
        marketId: true,
        securityType: true,
        price: { select: { marketCap: true } },
      },
      orderBy: { price: { marketCap: "desc" } },
      take: MAX_ASSETS,
    });

    // Compact wire format: arrays of parallel primitives beat an array of
    // objects for payload size and JSON parse time at 55k+ rows.
    const symbols: string[] = [];
    const names: string[] = [];
    const markets: string[] = [];
    const classes: string[] = [];

    for (const r of rows) {
      const sym = (r.symbol || "").trim().toUpperCase();
      const name = (r.name || "").trim();
      if (!sym || !name) continue;
      symbols.push(sym);
      names.push(name);
      markets.push(r.marketId);
      classes.push(assetClassOf(r.marketId, r.securityType));
    }

    return NextResponse.json({
      version: INDEX_VERSION,
      count: symbols.length,
      builtAt: Date.now(),
      symbols,
      names,
      markets,
      classes,
    });
  } catch (err) {
    console.error("[api/search/index] Error:", err);
    return NextResponse.json(
      { version: INDEX_VERSION, count: 0, builtAt: 0, symbols: [], names: [], markets: [], classes: [] },
      { status: 500 }
    );
  }
}
