import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { scoreNewsImportance, type ImportanceResult } from "@/lib/news/importance";
import { clusterNewsRows } from "@/lib/news/cluster";
import { fetchEconomicCalendar, type CalendarEvent } from "@/lib/economics/calendar";

export const dynamic = "force-dynamic";

// GET /api/news/alerts — the "High Alert" band: the strongest market-moving
// stories in the recent window, plus upcoming high-impact macro prints.
//
// Ranking is deterministic (lib/news/importance) and every alert carries its
// reasons. This endpoint NEVER invents a direction or a price target.

const CAL_CACHE_MS = 10 * 60 * 1000;
let calCache: { at: number; events: CalendarEvent[]; source: string } | null = null;

async function getCalendar(): Promise<{ events: CalendarEvent[]; source: string }> {
  if (calCache && Date.now() - calCache.at < CAL_CACHE_MS) {
    return { events: calCache.events, source: calCache.source };
  }
  try {
    const data = await fetchEconomicCalendar();
    calCache = { at: Date.now(), events: data.events ?? [], source: data.source };
    return { events: calCache.events, source: calCache.source };
  } catch (err) {
    console.error("[api/news/alerts] calendar unavailable:", err);
    // Honest: no calendar context rather than fabricated events.
    return { events: calCache?.events ?? [], source: calCache?.source ?? "unavailable" };
  }
}

function upcomingEvents(events: CalendarEvent[], now: number) {
  const horizonMs = 6 * 60 * 60 * 1000;
  return events
    .filter((e) => e.importance === "high")
    .map((e) => {
      const ts = Date.parse(e.date);
      return { event: e, ts };
    })
    .filter(({ ts }) => Number.isFinite(ts) && ts > now && ts - now <= horizonMs)
    .sort((a, b) => a.ts - b.ts)
    .slice(0, 3)
    .map(({ event, ts }) => ({
      id: event.id,
      title: event.title,
      country: event.country,
      date: event.date,
      minutesUntil: Math.max(1, Math.round((ts - now) / 60_000)),
      importance: event.importance,
      forecast: event.forecast,
      previous: event.previous,
    }));
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const now = Date.now();
  const limit = Math.min(10, Math.max(1, parseInt(searchParams.get("limit") || "5", 10)));
  const minScore = Math.max(0, Math.min(100, parseInt(searchParams.get("minScore") || "55", 10)));
  const hours = Math.min(72, Math.max(1, parseInt(searchParams.get("hours") || "24", 10)));
  const parseList = (v: string | null, cap: number) =>
    (v || "").split(",").map((t) => t.trim().toUpperCase()).filter(Boolean).slice(0, cap);
  const watchlist = parseList(searchParams.get("tickers"), 100);
  const portfolio = parseList(searchParams.get("portfolio"), 200);

  try {
    const [rows, calendar, job] = await Promise.all([
      prisma.newsItem.findMany({
        where: { timestamp: { gte: new Date(now - hours * 60 * 60 * 1000) } },
        orderBy: { timestamp: "desc" },
        take: 600,
      }),
      getCalendar(),
      prisma.cronJob.findUnique({ where: { type: "news_refresh" } }),
    ]);
    // The static fallback schedule carries placeholder dates, not confirmed
    // release times. Never present those as "CPI in 42m" — show nothing instead.
    const upcoming = calendar.source === "schedule-fallback"
      ? []
      : upcomingEvents(calendar.events, now);

    const scored = clusterNewsRows(rows)
      .map((row) => ({
        ...row,
        importance: scoreNewsImportance(row, { now, watchlist, portfolio }),
      }))
      .filter(
        ({ importance }) =>
          importance.score >= minScore &&
          (importance.level === "high" || importance.level === "critical"),
      )
      .sort((a, b) => {
        const d = b.importance.score - a.importance.score;
        if (d !== 0) return d;
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      })
      .slice(0, limit)
      .map((row) => {
        const imp: ImportanceResult = row.importance;
        return {
          id: row.id,
          source: row.source,
          headline: row.headline,
          summary: row.summary,
          url: row.url,
          ticker: row.ticker,
          category: row.category,
          region: row.region,
          tier: row.tier,
          sentiment: row.sentiment,
          timestamp: row.timestamp,
          sourceCount: row.sourceCount,
          clusterSources: row.clusterSources,
          importance: imp.score,
          alertLevel: imp.level,
          importanceReasons: imp.reasons,
          isBreaking: imp.isBreaking,
          confidence: imp.confidence,
          direction: imp.direction,
          horizon: imp.horizon,
          invalidates: imp.invalidates,
          affected: imp.affected,
        };
      });

    return NextResponse.json({
      alerts: scored,
      upcoming,
      calendarSource: calendar.source,
      threshold: minScore,
      lookbackHours: hours,
      lastIngestAt: job?.lastRunAt ?? null,
      generatedAt: new Date(now).toISOString(),
      source: "jdds",
    });
  } catch (err) {
    console.error("[api/news/alerts] Error:", err);
    return NextResponse.json(
      { alerts: [], upcoming: [], source: "error", error: "Could not scan the news database." },
      { status: 502 },
    );
  }
}
