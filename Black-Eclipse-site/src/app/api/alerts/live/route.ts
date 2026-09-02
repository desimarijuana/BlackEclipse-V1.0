// Live feed for the /alerts page: recent in-app notices + per-watch status.
import { prisma } from "@/lib/db";
import { recentNotices } from "@/lib/alerts/notifier";

export const dynamic = "force-dynamic";

// GET /api/alerts/live — in-app notices (recent 100) + watch statuses.
export async function GET() {
  try {
    const watches = await prisma.priceAlert.findMany({
      select: { id: true, name: true, status: true, statusMsg: true, active: true, lastEvalAt: true, lastFiredAt: true },
    });
    const events = await prisma.priceAlertEvent.findMany({
      orderBy: { firedAt: "desc" },
      take: 50,
    });
    return Response.json({ watches, events, notices: recentNotices() });
  } catch (err) {
    console.error("[api/alerts/live] GET error:", err);
    return Response.json({ error: "failed" }, { status: 500 });
  }
}