// ── GET /api/search/global ──────────────────────────────────────────────────
// Aggregates server-side data (journal strategies/setups/tags/trades, news
// headlines, research reports, saved blueprint pages) into compact SearchEntity
// rows for the global search bar. The client fetches this once and merges it
// into the resolver. Deterministic — no LLM.

import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getOrCreateProfile, listSetups, listStrategies, listTags } from "@/lib/journal/data";
import { HARNESS_PY_URL } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { isDashboardMirrorPath } from "@/lib/ui-engineering/live-page";

export const dynamic = "force-dynamic";

interface EntityRow {
  id: string;
  kind: "user" | "report" | "doc";
  title: string;
  keywords: string[];
  icon: string;
  tab: string;
  params?: Record<string, string>;
  deepLink?: string;
  subtitle: string;
}

export async function GET() {
  try {
    const entities: EntityRow[] = [];

    // ── Journal strategies / setups / tags ─────────────────────────────────
    try {
      const profileId = await getOrCreateProfile();
      const [strategies, setups, tags] = await Promise.all([
        listStrategies(profileId),
        listSetups(profileId),
        listTags(profileId),
      ]);
      for (const s of strategies) {
        entities.push({
          id: `strategy-${s.id}`,
          kind: "user",
          title: s.name,
          keywords: ["strategy", "playbook", s.name.toLowerCase()],
          icon: "book",
          tab: "journal",
          params: { strategy: s.id },
          subtitle: "Strategy · Journal",
        });
      }
      for (const s of setups) {
        entities.push({
          id: `setup-${s.id}`,
          kind: "user",
          title: s.name,
          keywords: ["setup", s.name.toLowerCase()],
          icon: "book",
          tab: "journal",
          params: { setup: s.id },
          subtitle: "Setup · Journal",
        });
      }
      for (const t of tags) {
        entities.push({
          id: `tag-${t.id}`,
          kind: "user",
          title: t.name,
          keywords: ["tag", t.name.toLowerCase()],
          icon: "book",
          tab: "journal",
          params: { tag: t.name },
          subtitle: "Tag · Journal",
        });
      }
    } catch (err) {
      console.error("[api/search/global] journal:", err);
    }

    // ── Journal trades (by symbol / notes) ─────────────────────────────────
    try {
      const profileId = await getOrCreateProfile();
      const trades = await prisma.trade.findMany({
        where: { profileId },
        select: { id: true, symbol: true, notes: true, direction: true, entryTime: true },
        orderBy: { entryTime: "desc" },
        take: 200,
      });
      for (const t of trades) {
        entities.push({
          id: `trade-${t.id}`,
          kind: "user",
          title: `${t.symbol} · ${t.direction}`,
          keywords: ["trade", t.symbol.toLowerCase(), (t.notes || "").toLowerCase()],
          icon: "chart",
          tab: "journal",
          params: { trade: t.id },
          subtitle: `Trade · ${new Date(t.entryTime).toISOString().slice(0, 10)}`,
        });
      }
    } catch (err) {
      console.error("[api/search/global] trades:", err);
    }

    // ── News headlines ─────────────────────────────────────────────────────
    try {
      const news = await prisma.newsItem.findMany({
        select: { id: true, headline: true, ticker: true, timestamp: true },
        orderBy: { timestamp: "desc" },
        take: 100,
      });
      for (const n of news) {
        entities.push({
          id: `news-${n.id}`,
          kind: "doc",
          title: n.headline,
          keywords: ["news", (n.ticker || "").toLowerCase(), n.headline.toLowerCase()],
          icon: "news",
          tab: "news",
          subtitle: `News · ${new Date(n.timestamp).toISOString().slice(0, 10)}`,
        });
      }
    } catch (err) {
      console.error("[api/search/global] news:", err);
    }

    // ── Research reports ─────────────────────────────────────────────────────
    // ─── Saved (blueprint) pages ─────────────────────────────────────────────
    // The pages the user or the agent authored are real destinations, so they
    // belong in ⌘K too. Best-effort: any runtime failure is swallowed and the
    // rest of the payload still returns. Dashboard mirrors are excluded (they
    // are agent-readable board snapshots, not user pages).
    try {
      const token = runtimeCallbackToken();
      // The SDK list endpoint: operator token, and it already excludes the
      // Command Center dashboard mirrors (`/dashboard/dash-*`).
      const res = await fetch(`${HARNESS_PY_URL}/sdk/pages`, {
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-Harness-Operator": token } : {}),
        },
        signal: AbortSignal.timeout(10_000),
        cache: "no-store",
      });
      if (res.ok) {
        const d = (await res.json().catch(() => ({}))) as {
          blueprints?: Array<{ id: string; title?: string; path?: string | null }>;
        };
        for (const b of d.blueprints ?? []) {
          if (!b?.id || !b.title || isDashboardMirrorPath(b.path)) continue;
          entities.push({
            id: `page-blueprint-${b.id}`,
            kind: "user",
            title: b.title,
            keywords: ["page", "saved page", b.title.toLowerCase()],
            icon: "pages",
            tab: "pages",
            params: { page: b.id },
            deepLink: `/?tab=pages&page=${encodeURIComponent(b.id)}`,
            subtitle: "Saved page",
          });
        }
      }
    } catch (err) {
      console.error("[api/search/global] pages:", err);
    }

    try {
      const reports = await prisma.researchReport.findMany({
        select: { id: true, query: true, ticker: true, status: true, createdAt: true },
        orderBy: { createdAt: "desc" },
        take: 50,
      });
      for (const r of reports) {
        entities.push({
          id: `report-${r.id}`,
          kind: "report",
          title: r.query,
          keywords: ["report", "research", (r.ticker || "").toLowerCase(), r.query.toLowerCase()],
          icon: "bot",
          tab: "chat",
          params: { report: r.id },
          subtitle: `Research · ${r.status}`,
        });
      }
    } catch (err) {
      console.error("[api/search/global] reports:", err);
    }

    return NextResponse.json({ entities });
  } catch (err) {
    console.error("[api/search/global] Error:", err);
    return NextResponse.json({ entities: [] }, { status: 500 });
  }
}
