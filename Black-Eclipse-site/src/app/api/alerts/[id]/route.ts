// Single-watch control: edit (restarts monitor), delete (stops monitor,
// KEEPS history), toggle active, fire a TEST alert through the full dispatch
// path, and fetch recent history + in-app notices for the live page.
import { prisma } from "@/lib/db";
import { startWatch, stopWatch } from "@/lib/alerts/alertMonitor";
import { dispatchAlert } from "@/lib/alerts/notifier";
import { checkMutationAllowed } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

// GET /api/alerts/:id — recent events + notices for one watch.
export async function GET(_request: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const [alert, events] = await Promise.all([
      prisma.priceAlert.findUnique({ where: { id } }),
      prisma.priceAlertEvent.findMany({ where: { alertId: id }, orderBy: { firedAt: "desc" }, take: 50 }),
    ]);
    if (!alert) return Response.json({ error: "not found" }, { status: 404 });
    return Response.json({
      alert: {
        ...alert,
        symbols: JSON.parse(alert.symbols),
        conditions: JSON.parse(alert.conditions),
        actions: JSON.parse(alert.actions || "{}"),
      },
      events,
    });
  } catch (err) {
    console.error("[api/alerts/:id] GET error:", err);
    return Response.json({ error: "failed" }, { status: 500 });
  }
}

// PUT /api/alerts/:id — edit fields; restarts the monitor. `active:false` in
// the body toggles off without deleting.
export async function PUT(request: Request, ctx: Ctx) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return Response.json({ error: guard.reason }, { status: 403 });
  const { id } = await ctx.params;
  try {
    const body = await request.json();
    const data: Record<string, unknown> = {};
    if (body.name !== undefined) data.name = String(body.name);
    if (body.symbols !== undefined) data.symbols = JSON.stringify(body.symbols);
    if (body.market !== undefined) data.market = String(body.market);
    if (body.conditions !== undefined) data.conditions = JSON.stringify(body.conditions);
    if (body.logic !== undefined) data.logic = body.logic === "OR" ? "OR" : "AND";
    if (body.timeframe !== undefined) data.timeframe = String(body.timeframe);
    if (body.dataSource !== undefined) data.dataSource = String(body.dataSource);
    if (body.intervalSec !== undefined) data.intervalSec = Math.max(30, Number(body.intervalSec) || 60);
    if (body.cooldownMin !== undefined) data.cooldownMin = Math.max(0, Number(body.cooldownMin) || 15);
    if (body.actions !== undefined) data.actions = JSON.stringify(body.actions);
    if (body.active !== undefined) data.active = Boolean(body.active);

    const updated = await prisma.priceAlert.update({ where: { id }, data });
    if (updated.active) {
      stopWatch(id);
      startWatch(id);
    } else {
      stopWatch(id);
    }
    return Response.json({ ok: true });
  } catch (err) {
    console.error("[api/alerts/:id] PUT error:", err);
    return Response.json({ error: "failed to update" }, { status: 500 });
  }
}

// DELETE /api/alerts/:id — stop monitoring, delete the watch, KEEP events.
export async function DELETE(request: Request, ctx: Ctx) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return Response.json({ error: guard.reason }, { status: 403 });
  const { id } = await ctx.params;
  try {
    stopWatch(id);
    await prisma.priceAlert.delete({ where: { id } });
    return Response.json({ ok: true });
  } catch (err) {
    console.error("[api/alerts/:id] DELETE error:", err);
    return Response.json({ error: "failed to delete" }, { status: 500 });
  }
}

// POST /api/alerts/:id — { action: "test" } fires a fake alert through the
// full dispatch path (symbol='TEST') so users can verify delivery.
export async function POST(request: Request, ctx: Ctx) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return Response.json({ error: guard.reason }, { status: 403 });
  const { id } = await ctx.params;
  try {
    const body = await request.json().catch(() => ({}));
    if (body?.action !== "test") {
      return Response.json({ error: "unknown action" }, { status: 400 });
    }
    const alert = await prisma.priceAlert.findUnique({ where: { id } });
    if (!alert) return Response.json({ error: "not found" }, { status: 404 });
    const result = await dispatchAlert({
      alertId: id,
      alertName: alert.name,
      symbols: ["TEST"],
      details: [{ indicator: "TEST", op: "manual", ok: true }],
      test: true,
    });
    await prisma.priceAlert.update({
      where: { id },
      data: { lastFiredAt: new Date() },
    });
    return Response.json(result);
  } catch (err) {
    console.error("[api/alerts/:id] POST error:", err);
    return Response.json({ error: "test dispatch failed" }, { status: 500 });
  }
}
