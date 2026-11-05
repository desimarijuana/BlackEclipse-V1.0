import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { checkMutationAllowed } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// POST /api/notifications — archive one or more raised notifications.
//
// The in-app ledger is instant and local; this endpoint is its durable mirror.
// Producers send the same stable id they use for dedupe, so an upsert is
// idempotent: replays, retries and the one-time local backfill never duplicate.
//
// Body: { items: NotificationInput[] } (a single object is accepted too).

const KINDS = new Set(["alert", "task", "approval", "agent", "bot"]);
const MAX_BATCH = 100;
const MAX_TITLE = 500;
const MAX_BODY = 4000;
const MAX_ID = 200;
const MAX_TAB = 40;

interface Row {
  id: string;
  tab: string;
  kind: string;
  title: string;
  body: string;
  at: Date;
  read: boolean;
}

function str(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return trimmed.slice(0, max);
}

function normalize(raw: unknown): Row | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id, MAX_ID);
  const title = str(r.title, MAX_TITLE);
  if (!id || !title) return null;
  const tab = str(r.tab, MAX_TAB) ?? "alerts";
  const kind = typeof r.kind === "string" && KINDS.has(r.kind) ? r.kind : "alert";
  const body = typeof r.body === "string" ? r.body.slice(0, MAX_BODY) : "";
  const atRaw = typeof r.at === "number" ? r.at : typeof r.at === "string" ? Date.parse(r.at) : NaN;
  const at = Number.isFinite(atRaw) ? new Date(atRaw) : new Date();
  return { id, tab, kind, title, body, at, read: r.read === true };
}

export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return NextResponse.json({ error: guard.reason }, { status: 403 });

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const rec = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  const rawItems = Array.isArray(rec.items)
    ? rec.items
    : Array.isArray(payload)
      ? payload
      : [rec.notification ?? rec];

  const rows = rawItems
    .map(normalize)
    .filter((r): r is Row => r !== null)
    .slice(0, MAX_BATCH);

  if (rows.length === 0) return NextResponse.json({ saved: 0 });

  let saved = 0;
  for (const row of rows) {
    try {
      await prisma.appNotification.upsert({
        where: { id: row.id },
        create: row,
        update: {},
      });
      saved++;
    } catch (err) {
      // One bad row must not lose the rest of the batch.
      console.error("[api/notifications] upsert failed:", err);
    }
  }

  return NextResponse.json({ saved });
}
