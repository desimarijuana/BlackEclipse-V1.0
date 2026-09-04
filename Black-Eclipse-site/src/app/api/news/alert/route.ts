import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { startWatch } from "@/lib/alerts/alertMonitor";
import { checkMutationAllowed } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

/**
 * POST /api/news/alert — one-click alert from a news card.
 * Body: { ticker, direction: "up" | "down", movePct?: number }
 *
 * Creates a CHANGE_PCT watch for the article's ticker reusing the existing
 * PriceAlert engine, then starts its poll monitor.
 */
export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return NextResponse.json({ error: guard.reason }, { status: 403 });

  try {
    const body = await request.json();
    const ticker = String(body?.ticker || "").trim().toUpperCase();
    const direction = body?.direction === "down" ? "down" : "up";
    const movePct = Math.min(50, Math.max(0.5, Number(body?.movePct) || 2));

    if (!ticker) {
      return NextResponse.json({ error: "ticker required" }, { status: 400 });
    }

    // Verify the symbol exists in the universe so the alert can get data.
    const asset = await prisma.asset.findFirst({
      where: { symbol: ticker, isActive: true },
      select: { marketId: true },
    });
    const market = asset?.marketId || "US";

    const created = await prisma.priceAlert.create({
      data: {
        name: `${ticker} ${direction === "up" ? "rally" : "drop"} ≥ ${movePct}% (from news)`,
        symbols: JSON.stringify([ticker]),
        market,
        universe: "CUSTOM",
        conditions: JSON.stringify([
          {
            indicator: "CHANGE_PCT",
            operator: direction === "up" ? ">" : "<",
            compareMode: "value",
            value: direction === "up" ? movePct : -movePct,
          },
        ]),
        logic: "AND",
        timeframe: "1d",
        dataSource: "Auto",
        mode: "poll",
        intervalSec: 60,
        cooldownMin: 15,
        actions: JSON.stringify({ toast: true }),
        active: true,
      },
    });
    startWatch(created.id);

    return NextResponse.json({ success: true, alert: { id: created.id, name: created.name } }, { status: 201 });
  } catch (err) {
    console.error("[api/news/alert] Error:", err);
    return NextResponse.json({ error: "failed to create alert" }, { status: 500 });
  }
}