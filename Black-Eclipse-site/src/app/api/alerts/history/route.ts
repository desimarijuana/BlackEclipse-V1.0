import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/alerts/history — the unified, searchable alert archive.
//
// Sources:
//   · AppNotification — every notification raised in the app (news/price
//     alerts, approval requests, tasks, agent runs, bots), written by the
//     ledger's durable mirror.
//   · PriceAlertEvent — the price-alert engine's own fire log. Older rows
//     predate AppNotification, so the union keeps the full history instead of
//     showing only what happened after the archive shipped.
//
// Query: q, kind (alert|task|approval|agent|bot), tab, range (24h|7d|30d|all),
//        limit, offset.

const RANGE_HOURS: Record<string, number> = { "24h": 24, "7d": 168, "30d": 720 };

const KINDS = new Set(["alert", "task", "approval", "agent", "bot"]);

interface Row {
  id: string;
  tab: string;
  kind: string;
  title: string;
  body: string;
  at: string;
  read: boolean;
  legacy: boolean;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = (searchParams.get("q") || "").trim().slice(0, 200);
  const kindParam = (searchParams.get("kind") || "").trim();
  const kind = KINDS.has(kindParam) ? kindParam : "";
  const tab = (searchParams.get("tab") || "").trim().slice(0, 40);
  const range = searchParams.get("range") || "30d";
  const limit = Math.min(200, Math.max(1, parseInt(searchParams.get("limit") || "100", 10)));
  const offset = Math.max(0, parseInt(searchParams.get("offset") || "0", 10));
  const take = Math.min(2000, limit + offset);

  const since = RANGE_HOURS[range] ? new Date(Date.now() - RANGE_HOURS[range] * 3600_000) : null;

  const appWhere: Record<string, unknown> = {};
  if (kind) appWhere.kind = kind;
  if (tab) appWhere.tab = tab;
  if (since) appWhere.at = { gte: since };
  if (q) appWhere.OR = [{ title: { contains: q } }, { body: { contains: q } }];

  // Price events are kind=alert in tab=alerts. Skip the union when either
  // filter excludes them, so a News/Task/Agent view never mixes engine rows in.
  const wantPrice = (!kind || kind === "alert") && (!tab || tab === "alerts");
  const priceWhere: Record<string, unknown> = {};
  if (since) priceWhere.firedAt = { gte: since };
  if (q) priceWhere.OR = [{ detail: { contains: q } }, { symbol: { contains: q } }];

  try {
    const [archive, priceEvents] = await Promise.all([
      prisma.appNotification.findMany({ where: appWhere, orderBy: { at: "desc" }, take }),
      wantPrice
        ? prisma.priceAlertEvent.findMany({ where: priceWhere, orderBy: { firedAt: "desc" }, take })
        : Promise.resolve([]),
    ]);

    const seen = new Set(archive.map((n) => n.id));
    const rows: Row[] = archive.map((n) => ({
      id: n.id,
      tab: n.tab,
      kind: n.kind,
      title: n.title,
      body: n.body,
      at: n.at.toISOString(),
      read: n.read,
      legacy: false,
    }));

    for (const e of priceEvents) {
      if (seen.has(e.id)) continue; // already archived with the same producer id
      seen.add(e.id);
      rows.push({
        id: e.id,
        tab: "alerts",
        kind: "alert",
        title: e.symbol,
        body: e.detail,
        at: e.firedAt.toISOString(),
        read: true,
        legacy: true,
      });
    }

    rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
    return NextResponse.json({
      alerts: rows.slice(offset, offset + limit),
      total: rows.length,
      capped: rows.length >= take,
      range,
    });
  } catch (err) {
    console.error("[api/alerts/history] GET error:", err);
    return NextResponse.json(
      { alerts: [], total: 0, error: "Could not read alert history." },
      { status: 502 },
    );
  }
}
