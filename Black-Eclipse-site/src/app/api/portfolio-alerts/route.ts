import { NextResponse } from "next/server";
import { getRegisteredAlerts, setRegisteredAlerts, type StoredAlert } from "@/lib/alerts-evaluator";

export const dynamic = "force-dynamic";

// GET /api/portfolio-alerts?clientId=… — triggered alert marks for a client.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const clientId = (searchParams.get("clientId") || "").trim();
  if (!clientId) return NextResponse.json({ triggered: [] });
  const registry = await getRegisteredAlerts();
  const alerts = registry[clientId] ?? [];
  return NextResponse.json({
    triggered: alerts.filter(a => a.id.endsWith("_triggered")).map(a => a.id.replace("_triggered", "")),
  });
}

// POST /api/portfolio-alerts — register/replace a client's alert ledger.
// Body: { clientId, alerts: StoredAlert[] }
export async function POST(request: Request) {
  try {
    const body = await request.json() as { clientId?: string; alerts?: StoredAlert[] };
    const clientId = (body.clientId || "").trim();
    if (!clientId || !Array.isArray(body.alerts)) {
      return NextResponse.json({ error: "clientId and alerts required" }, { status: 400 });
    }
    const registry = await getRegisteredAlerts();
    registry[clientId] = body.alerts.slice(0, 200);
    await setRegisteredAlerts(registry);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/portfolio-alerts] POST error:", err);
    return NextResponse.json({ error: "internal" }, { status: 500 });
  }
}