// ─── News alert policy (server-side) ────────────────────────────────────────
// Controls the background "high alert" scan that pushes market-moving stories
// through the existing notification channels. Kept in SystemConfig so it is
// editable from Settings and survives restarts.

import { getConfigJSON, setConfigJSON } from "@/lib/settings";

export interface NewsAlertPolicy {
  enabled: boolean;
  /** Minimum importance score (0..100) that may fire a push. */
  minScore: number;
  /** Only consider articles published within this window. */
  lookbackMinutes: number;
  /** Cap pushes per scan cycle so a burst cannot spam. */
  maxPerCycle: number;
  /** Optional category allow-list; empty means every category. */
  categories: string[];
  /** Optional personal tickers — a matching story gets a relevance boost. */
  tickers: string[];
  /** Suppress pushes during these server-local hours. */
  quietHours: { enabled: boolean; startHour: number; endHour: number };
}

export const DEFAULT_NEWS_ALERT_POLICY: NewsAlertPolicy = {
  enabled: false,
  // Conservative default: only genuinely critical stories push until the user
  // explicitly lowers the threshold. The in-tab High Alert band still shows
  // "high" items regardless.
  minScore: 75,
  lookbackMinutes: 180,
  maxPerCycle: 3,
  categories: [],
  tickers: [],
  quietHours: { enabled: false, startHour: 22, endHour: 7 },
};

const POLICY_KEY = "news_alert_policy";

function sanitize(raw: Partial<NewsAlertPolicy>): NewsAlertPolicy {
  const d = DEFAULT_NEWS_ALERT_POLICY;
  const clamp = (n: unknown, lo: number, hi: number, fallback: number) => {
    const v = Number(n);
    return Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : fallback;
  };
  const qh = raw.quietHours ?? d.quietHours;
  return {
    enabled: raw.enabled === true,
    minScore: clamp(raw.minScore, 0, 100, d.minScore),
    lookbackMinutes: clamp(raw.lookbackMinutes, 5, 720, d.lookbackMinutes),
    maxPerCycle: clamp(raw.maxPerCycle, 1, 10, d.maxPerCycle),
    categories: Array.isArray(raw.categories)
      ? raw.categories.map((c) => String(c).toUpperCase()).filter(Boolean).slice(0, 30)
      : [],
    tickers: Array.isArray(raw.tickers)
      ? raw.tickers.map((t) => String(t).toUpperCase()).filter(Boolean).slice(0, 100)
      : [],
    quietHours: {
      enabled: qh.enabled === true,
      startHour: clamp(qh.startHour, 0, 23, d.quietHours.startHour),
      endHour: clamp(qh.endHour, 0, 23, d.quietHours.endHour),
    },
  };
}

export async function getNewsAlertPolicy(): Promise<NewsAlertPolicy> {
  const raw = await getConfigJSON<Partial<NewsAlertPolicy>>(POLICY_KEY, DEFAULT_NEWS_ALERT_POLICY);
  return sanitize(raw);
}

export async function setNewsAlertPolicy(patch: Partial<NewsAlertPolicy>): Promise<NewsAlertPolicy> {
  const current = await getNewsAlertPolicy();
  const next = sanitize({ ...current, ...patch, quietHours: { ...current.quietHours, ...patch.quietHours } });
  await setConfigJSON(POLICY_KEY, next);
  return next;
}

/** Whether the current server-local time falls inside the quiet window. */
export function isQuietNow(policy: NewsAlertPolicy, now = new Date()): boolean {
  if (!policy.quietHours.enabled) return false;
  const h = now.getHours();
  const { startHour, endHour } = policy.quietHours;
  if (startHour === endHour) return false;
  // Window may wrap midnight (e.g. 22 → 7).
  return startHour < endHour ? h >= startHour && h < endHour : h >= startHour || h < endHour;
}
