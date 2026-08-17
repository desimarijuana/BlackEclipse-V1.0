import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/markets — list markets loaded in JDDS with asset counts.
export async function GET() {
  try {
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

    return NextResponse.json({
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
    });
  } catch (err) {
    console.error("[api/markets] GET error:", err);
    return NextResponse.json({ error: "Failed to load markets" }, { status: 500 });
  }
}
