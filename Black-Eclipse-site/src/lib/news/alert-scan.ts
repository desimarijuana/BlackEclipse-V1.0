// ─── Background news alert scan ─────────────────────────────────────────────
// Runs after each ingest cycle. Scores recent stories deterministically and
// pushes the strongest few through the existing notification channels.
//
// Safety properties:
//   · First run SEEDS the seen-set instead of firing on history/backlog.
//   · Per-story dedupe means a story is delivered once, not every cycle.
//   · A per-cycle cap bounds a burst; unsent stories stay eligible next cycle.
//   · Disabled by default; the user opts in from Settings.
//   · Quiet hours are honoured in server-local time.

import { prisma } from "@/lib/db";
import { getConfigJSON, setConfigJSON } from "@/lib/settings";
import { clusterNewsRows } from "@/lib/news/cluster";
import { scoreNewsImportance } from "@/lib/news/importance";
import { getNewsAlertPolicy, isQuietNow } from "@/lib/news/alert-policy";
import { dispatchNewsAlert } from "@/lib/alerts/notifier";

const STATE_KEY = "news_alert_state";
const MAX_SEEN = 600;

interface NewsAlertState {
  initialized: boolean;
  notifiedIds: string[];
  lastScanAt: string | null;
}

const EMPTY_STATE: NewsAlertState = { initialized: false, notifiedIds: [], lastScanAt: null };

export interface NewsAlertScanResult {
  sent: number;
  considered: number;
  reason?: string;
}

export async function runNewsAlertScan(now = Date.now()): Promise<NewsAlertScanResult> {
  const policy = await getNewsAlertPolicy();
  if (!policy.enabled) return { sent: 0, considered: 0, reason: "disabled" };
  if (isQuietNow(policy, new Date(now))) return { sent: 0, considered: 0, reason: "quiet-hours" };

  const rows = await prisma.newsItem.findMany({
    where: { timestamp: { gte: new Date(now - policy.lookbackMinutes * 60_000) } },
    orderBy: { timestamp: "desc" },
    take: 400,
  });

  const categoryAllow = new Set(policy.categories);
  const scored = clusterNewsRows(rows)
    .map((row) => ({ row, importance: scoreNewsImportance(row, { now, watchlist: policy.tickers }) }))
    .filter(({ row, importance }) => {
      if (importance.score < policy.minScore) return false;
      if (importance.level !== "high" && importance.level !== "critical") return false;
      if (categoryAllow.size > 0 && !categoryAllow.has((row.category || "").toUpperCase())) return false;
      return true;
    })
    .sort((a, b) => {
      const d = b.importance.score - a.importance.score;
      if (d !== 0) return d;
      return new Date(b.row.timestamp).getTime() - new Date(a.row.timestamp).getTime();
    });

  const state = await getConfigJSON<NewsAlertState>(STATE_KEY, EMPTY_STATE);
  const known = new Set(state.notifiedIds);
  const fresh = scored.filter(({ row }) => !known.has(row.id));

  // Backlog guard: the first scan establishes a baseline and sends nothing.
  if (!state.initialized) {
    await setConfigJSON(STATE_KEY, {
      initialized: true,
      notifiedIds: fresh.map(({ row }) => row.id).slice(0, MAX_SEEN),
      lastScanAt: new Date(now).toISOString(),
    } satisfies NewsAlertState);
    return { sent: 0, considered: scored.length, reason: "seeded" };
  }

  const toSend = fresh.slice(0, policy.maxPerCycle);
  let sent = 0;
  for (const { row, importance } of toSend) {
    try {
      await dispatchNewsAlert({
        id: row.id,
        headline: row.headline,
        level: importance.level === "critical" ? "critical" : "high",
        score: importance.score,
        source: row.source,
        reasons: importance.reasons,
        ageMinutes: Math.max(0, Math.round((now - new Date(row.timestamp).getTime()) / 60_000)),
        ticker: row.ticker,
        url: row.url,
      });
      sent++;
    } catch (err) {
      console.error("[news-alert-scan] dispatch failed:", err);
    }
  }

  const notifiedIds = Array.from(new Set([...state.notifiedIds, ...toSend.map(({ row }) => row.id)]))
    .slice(-MAX_SEEN);
  await setConfigJSON(STATE_KEY, {
    initialized: true,
    notifiedIds,
    lastScanAt: new Date(now).toISOString(),
  } satisfies NewsAlertState);

  return { sent, considered: scored.length };
}
