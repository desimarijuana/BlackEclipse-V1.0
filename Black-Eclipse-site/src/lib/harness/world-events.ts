// ── JDdS bridge — world-state events (Investor Eye) ──────────────────────────
// Read normalized world events (GeopoliticalEvent) for the Python agent's
// `get_world_events` tool. Kept in its own module so the large `data-bridge.ts`
// dispatcher stays within its size budget (the size guard is real, and this is a
// genuine grow — the implementation lives where it belongs instead).
//
// Read-only, bounded, honest: an unreadable store is a `source_failure` (never
// "no events happened"), and an absent id is `not_found`.

import { prisma } from "@/lib/db";
import type { DataBridgeResult } from "./data-bridge-types";

function parseWorldArray(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

function mapWorldRow(row: {
  id: string; dedupKey: string; title: string; summary: string | null;
  eventType: string; category: string | null; severity: string;
  countries: string; placeName: string | null; lon: number | null; lat: number | null;
  publishedAt: Date; sourceCount: number; primarySource: string;
  relevance: number; channels: string; commodities: string; sectors: string; sources: string;
}): Record<string, unknown> {
  return {
    id: row.id,
    dedupKey: row.dedupKey,
    title: row.title,
    summary: row.summary,
    eventType: row.eventType,
    category: row.category,
    severity: row.severity,
    countries: parseWorldArray(row.countries),
    placeName: row.placeName,
    lon: row.lon,
    lat: row.lat,
    publishedAt: row.publishedAt.toISOString(),
    sourceCount: row.sourceCount,
    primarySource: row.primarySource,
    relevance: row.relevance,
    channels: parseWorldArray(row.channels),
    commodities: parseWorldArray(row.commodities),
    sectors: parseWorldArray(row.sectors),
    sources: (() => {
      try {
        const v = JSON.parse(row.sources);
        return Array.isArray(v) ? v : [];
      } catch {
        return [];
      }
    })(),
  };
}

export async function worldEvents(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const hoursRaw = Number(params.hours);
  const hours = Number.isFinite(hoursRaw) ? Math.min(Math.max(hoursRaw, 1), 24 * 90) : 168;
  const limitRaw = Number(params.limit);
  const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(Math.trunc(limitRaw), 1), 200) : 60;
  const id = String(params.id ?? "").trim();
  const since = new Date(Date.now() - hours * 3600_000);

  try {
    if (id) {
      const row = await prisma.geopoliticalEvent.findFirst({ where: { OR: [{ id }, { dedupKey: id }] } });
      if (!row) return { status: "OK", failureClass: "not_found", event: null };
      return { status: "OK", event: mapWorldRow(row) };
    }
    const type = String(params.type ?? "").trim();
    const severity = String(params.severity ?? "").trim();
    const rows = await prisma.geopoliticalEvent.findMany({
      where: {
        publishedAt: { gte: since },
        ...(type ? { eventType: type } : {}),
        ...(severity ? { severity } : {}),
      },
      // Rank by investor relevance then recency, exactly as the UI query does.
      orderBy: [{ relevance: "desc" }, { publishedAt: "desc" }],
      take: limit,
    });
    let events = rows.map(mapWorldRow);
    const iso2 = String(params.iso2 ?? "").trim().toUpperCase();
    if (iso2) {
      events = events.filter((e) => Array.isArray(e.countries) && (e.countries as string[]).includes(iso2));
    }
    const text = String(params.text ?? "").trim().toLowerCase();
    if (text) {
      events = events.filter((e) =>
        `${String(e.title)} ${String(e.placeName ?? "")}`.toLowerCase().includes(text));
    }
    return { status: "OK", count: events.length, hours, events };
  } catch (err) {
    console.error("[data-bridge] world_events read failed:", err);
    return {
      status: "UNAVAILABLE",
      failureClass: "source_failure",
      error: `geopolitical event store read failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
