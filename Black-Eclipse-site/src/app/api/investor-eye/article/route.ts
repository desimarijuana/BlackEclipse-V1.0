import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { rowToEvent } from "@/lib/investor-eye/state";
import { resolveEventArticleMeta } from "@/lib/investor-eye/article-meta-fetch";
import { guardExpensiveMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

/**
 * GET /api/investor-eye/article?id=<eventId>
 *
 * Recovers the real headline/description for an event whose provider publishes
 * none (GDELT has only URLs). Fetches the article's Open Graph metadata through
 * the shared guarded transport and caches the result permanently, so any URL is
 * read at most once.
 *
 * Only the FIRST caller pays the network cost; every later open is served from
 * the cache. Guarded as an expensive mutation because it performs outbound I/O.
 *
 * Honest by design: a paywall, bot wall, timeout or non-HTML response all yield
 * `available: false`, and the UI keeps stating that no headline is available.
 */
export async function GET(request: Request) {
  // Outbound network I/O — rate-limit like the other fetch-performing routes.
  const blocked = guardExpensiveMutation(request, "investor-eye-article", { limit: 60, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }

  const id = new URL(request.url).searchParams.get("id");
  if (!id) return NextResponse.json({ available: false, note: "id is required" }, { status: 400 });

  try {
    const row = await prisma.geopoliticalEvent.findFirst({
      where: { OR: [{ id }, { dedupKey: id }] },
      select: { id: true, dedupKey: true, title: true, summary: true, eventType: true, severity: true,
        channels: true, commodities: true, sectors: true, securities: true, countries: true,
        lon: true, lat: true, confidence: true, relevance: true, relevanceReasons: true,
        sourceCount: true, sources: true, primarySource: true, publishedAt: true, firstSeen: true,
        lastUpdated: true, status: true, headline: true, description: true },
    });
    if (!row) {
      return NextResponse.json({ available: false, note: "Event not found." }, { status: 404 });
    }

    const event = rowToEvent(row);

    // A source-provided headline already exists (news events) — nothing to fetch.
    if (event.headline) {
      return NextResponse.json({
        available: true,
        cached: true,
        source: "event",
        headline: event.headline,
        description: event.description ?? null,
      });
    }

    const urls = event.sources.map((s) => s.url);
    const { meta, url, cached } = await resolveEventArticleMeta(urls);

    if (!meta) {
      return NextResponse.json({
        available: false,
        cached,
        note: urls.length === 0
          ? "This event carries no source URL to read."
          : "The linked article did not expose a headline (paywall, block or non-HTML page).",
        attempted: Math.min(urls.length, 3),
      });
    }

    return NextResponse.json({
      available: true,
      cached,
      source: "article",
      headline: meta.title,
      description: meta.description ?? null,
      titleSource: meta.titleSource,
      siteName: meta.siteName ?? null,
      url,
    });
  } catch (err) {
    console.error("[api/investor-eye/article] error:", err);
    return NextResponse.json({ available: false, note: "Could not read the article." });
  }
}
