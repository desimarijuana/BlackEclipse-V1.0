// CRUD + control API for price/condition alert watches.
import { prisma } from "@/lib/db";
import { startWatch, runningWatchCount } from "@/lib/alerts/alertMonitor";
import { checkMutationAllowed } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

function serialize(a: {
  id: string; name: string; symbols: string; market: string; universe: string;
  conditions: string; logic: string; timeframe: string; dataSource: string;
  mode: string; intervalSec: number; cooldownMin: number; actions: string;
  active: boolean; status: string; statusMsg: string | null;
  lastEvalAt: Date | null; lastFiredAt: Date | null;
}) {
  return {
    ...a,
    symbols: JSON.parse(a.symbols || "[]") as string[],
    conditions: JSON.parse(a.conditions || "[]"),
    actions: JSON.parse(a.actions || "{}"),
  };
}

// GET /api/alerts — list watches + running monitor count.
export async function GET() {
  try {
    const alerts = await prisma.priceAlert.findMany({ orderBy: { createdAt: "desc" } });
    return Response.json({ alerts: alerts.map(serialize), running: runningWatchCount() });
  } catch (err) {
    console.error("[api/alerts] GET error:", err);
    return Response.json({ error: "failed to load alerts" }, { status: 500 });
  }
}

// POST /api/alerts — create a watch (starts its monitor).
export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) {
    return Response.json({ error: guard.reason }, { status: 403 });
  }
  try {
    const body = await request.json();
    if (!body?.name || !Array.isArray(body?.symbols) || body.symbols.length === 0 || !Array.isArray(body?.conditions)) {
      return Response.json({ error: "name, symbols[], conditions[] required" }, { status: 400 });
    }
    const created = await prisma.priceAlert.create({
      data: {
        name: String(body.name),
        symbols: JSON.stringify(body.symbols),
        market: String(body.market || "US"),
        universe: String(body.universe || "CUSTOM"),
        conditions: JSON.stringify(body.conditions),
        logic: body.logic === "OR" ? "OR" : "AND",
        timeframe: String(body.timeframe || "1d"),
        dataSource: String(body.dataSource || "Auto"),
        mode: "poll",
        intervalSec: Math.max(30, Number(body.intervalSec) || 60),
        cooldownMin: Math.max(0, Number(body.cooldownMin) || 15),
        actions: JSON.stringify(body.actions || {}),
        active: body.active !== false,
      },
    });
    if (created.active) startWatch(created.id);
    return Response.json({ alert: serialize(created) }, { status: 201 });
  } catch (err) {
    console.error("[api/alerts] POST error:", err);
    return Response.json({ error: "failed to create alert" }, { status: 500 });
  }
}
