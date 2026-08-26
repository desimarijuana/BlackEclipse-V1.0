import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

type MarketsPayload = {
  markets: Array<{
    id: string;
    country: string;
    exchange: string;
    timezone: string | null;
    isCrypto: boolean;
    enabled: boolean;
    assetCount: number;
    pricedCount: number;
  }>;
};

// In-memory SWR cache. Market counts barely change minute-to-minute, and the
// underlying SQLite writes are synchronous — a cold count query during a
// background universe sync used to block the event loop for 100s+ and freeze
// every other request. Serve cached instantly; rebuild in the background.
const CACHE_TTL_MS = 5 * 60 * 1000;
let marketsCache: { t: number; data: MarketsPayload } | null = null;
let rebuildInFlight = false;

async function buildMarketsPayload(): Promise<MarketsPayload> {
  const markets = await prisma.market.findMany({
    orderBy: { country: "asc" },
    include: {
      _count: { select: { assets: true } },
    },
  });

  const withPrices = await prisma.asset.groupBy({
    by: ["marketId"],
    where: { price: { isNot: null } },
    _count: { _all: true },
  });
  const pricedCount = new Map(withPrices.map((r) => [r.marketId, r._count._all]));

  return {
    markets: markets.map((m) => ({
      id: m.id,
      country: m.country,
      exchange: m.exchange,
      timezone: m.timezone,
      isCrypto: m.isCrypto,
      enabled: m.enabled,
      assetCount: m._count.assets,
      pricedCount: pricedCount.get(m.id) ?? 0,
    })),
  };
}

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildMarketsPayload()
    .then((data) => {
      marketsCache = { t: Date.now(), data };
    })
    .catch((err) => console.error("[api/markets] background rebuild error:", err))
    .finally(() => {
      rebuildInFlight = false;
    });
}

// GET /api/markets — list markets loaded in JDDS with asset counts.
export async function GET() {
  try {
    if (marketsCache) {
      if (Date.now() - marketsCache.t < CACHE_TTL_MS) {
        return NextResponse.json(marketsCache.data);
      }
      // Stale — serve it now and refresh quietly.
      startBackgroundRebuild();
      return NextResponse.json(marketsCache.data);
    }

    const data = await buildMarketsPayload();
    marketsCache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/markets] GET error:", err);
    return NextResponse.json({ error: "Failed to load markets" }, { status: 500 });
  }
}
