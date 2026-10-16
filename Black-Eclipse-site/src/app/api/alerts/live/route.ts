// Live feed for the /alerts page: recent in-app notices + per-watch status.
import { prisma } from "@/lib/db";
import { getAlertChannels } from "@/lib/alerts/notifier";

export const dynamic = "force-dynamic";

// GET /api/alerts/live — in-app notices (latest 100) + watch statuses + events.
// Notices are DERIVED from the durable `PriceAlertEvent` rows (not an
// in-process ring buffer), so they survive a restart and never diverge across
// workers: one durable record, two views. The Settings "in-app" toggle gates
// the notice list (the toast/desktop layer is client-side and separate).
export async function GET() {
  try {
    const [watches, events, channels] = await Promise.all([
      prisma.priceAlert.findMany({
        select: { id: true, name: true, status: true, statusMsg: true, active: true, lastEvalAt: true, lastFiredAt: true },
      }),
      prisma.priceAlertEvent.findMany({
        orderBy: { firedAt: "desc" },
        take: 50,
      }),
      getAlertChannels(),
    ]);
    const notices = channels.inApp
      ? events.slice(0, 100).map((e) => ({
          msg: e.detail,
          firedAt: e.firedAt,
          test: e.detail.startsWith("TEST —"),
        }))
      : [];
    return Response.json({ watches, events, notices });
  } catch (err) {
    console.error("[api/alerts/live] GET error:", err);
    return Response.json({ error: "failed" }, { status: 500 });
  }
}