import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { marketDisplayName } from "@/lib/markets";

export const dynamic = "force-dynamic";

// Enough rows for the customizable overview (users can show up to this many
// per market); the UI decides how many to actually render.
const TOP_PER_MARKET = 10;

type OverviewGroup = {
  id: string;
  country: string;
  /** Human-readable market name (e.g. "Pakistan", "United States"). */
  name?: string;
  exchange: string;
  isCrypto: boolean;
  currency: string;
  indexName?: string;
  stocks: Array<{ symbol: string; name: string; price: number; changePct: number; marketCap: number | null }>;
};

async function buildOverview(): Promise<{ groups: OverviewGroup[] }> {
  const markets = await prisma.market.findMany({
    where: { enabled: true },
    orderBy: { country: "asc" },
    select: { id: true, country: true, exchange: true, isCrypto: true },
  });

  const groups = await Promise.all(
    markets.map(async (m): Promise<OverviewGroup | null> => {
      const assets = await prisma.asset.findMany({
        where: { marketId: m.id, isActive: true, price: { isNot: null } },
        orderBy: m.isCrypto
          ? [{ price: { rank: { sort: "asc", nulls: "last" } } }]
          : [{ price: { marketCap: { sort: "desc", nulls: "last" } } }],
        take: TOP_PER_MARKET,
        select: {
          symbol: true,
          name: true,
          price: { select: { price: true, changePct: true, marketCap: true } },
        },
      });
      const stocks = assets
        .filter((a) => a.price && a.price.price > 0)
        .map((a) => ({
          symbol: a.symbol,
          name: a.name,
          price: a.price!.price,
          changePct: a.price!.changePct,
          marketCap: a.price!.marketCap,
        }));
      if (stocks.length === 0) return null;
      return {
        id: m.id,
        country: m.country,
        name: marketDisplayName(m.id),
        exchange: m.exchange,
        isCrypto: m.isCrypto,
        currency: MARKET_CURRENCY[m.id] || "$",
        stocks,
      };
    })
  );

  return { groups: groups.filter((g): g is OverviewGroup => g !== null) };
}

// In-memory SWR cache — the overview aggregates every market on each build and
// counts/prices move slowly, so serve instantly and refresh in the background.
const CACHE_TTL_MS = 5 * 60 * 1000;
let cache: { t: number; data: { groups: OverviewGroup[] } } | null = null;
let rebuildInFlight = false;

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildOverview()
    .then((data) => {
      cache = { t: Date.now(), data };
    })
    .catch((err) => console.error("[api/global-overview] background rebuild error:", err))
    .finally(() => {
      rebuildInFlight = false;
    });
}

// GET /api/global-overview — top stocks (by market cap; crypto by rank) for
// every priced market in JDDS. Powers the Global Markets overview tables so
// users can see at a glance what is moving across world markets.
export async function GET() {
  try {
    if (cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) {
        return NextResponse.json(cache.data);
      }
      startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    const data = await buildOverview();
    cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/global-overview] GET error:", err);
    return NextResponse.json({ groups: [] }, { status: 500 });
  }
}
