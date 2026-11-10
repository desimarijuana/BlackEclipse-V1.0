// ── High-alert news → notification diff ─────────────────────────────────────
// Pure helpers for the root-mounted `NewsAlertWatcher`.
//
// The News tab no longer renders a separate High Alert band: high-level stories
// are part of the normal feed, ranked most-critical first. The same stories are
// also surfaced in the header ledger so an operator sees them from any tab.
//
// The first poll SEEDS the seen set without notifying — booting the app never
// replays a toast backlog, and the header ledger is not filled with historical
// news that pushes the operator's price alerts / task events out of view. Later
// polls announce only stories and upcoming high-impact releases that were not
// seen before. This matches the task/bot/price watchers.

/** Ring capacity for remembered notification ids. */
export const MAX_SEEN_NEWS_NOTIFICATIONS = 500;

/** Only imminent releases are worth a notification; the API window is wider. */
export const EVENT_NOTIFY_HORIZON_MINUTES = 90;

export interface WatchedNewsAlert {
  id: string;
  headline: string;
  alertLevel?: string | null;
  importance?: number | null;
  source?: string | null;
  ticker?: string | null;
  timestamp?: string | null;
  /** Original article link from the alerts payload. */
  url?: string | null;
}

export interface WatchedNewsEvent {
  id: string;
  title: string;
  country?: string | null;
  minutesUntil?: number | null;
  date?: string | null;
  forecast?: string | null;
  previous?: string | null;
}

export interface NewsNotification {
  /** Stable dedupe key (`news:<id>` / `news-event:<id>`). */
  id: string;
  title: string;
  body: string;
  /** The story's original source link, when the row carries one. */
  url?: string;
}

/** Only absolute http(s) story links are kept — never a relative feed path. */
function sourceUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value.trim());
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function levelLabel(level: string | null | undefined): string {
  switch ((level || '').toLowerCase()) {
    case 'critical':
      return 'CRITICAL';
    case 'high':
      return 'HIGH ALERT';
    case 'medium':
      return 'WATCH';
    default:
      return 'NEWS';
  }
}

/** Turn the alerts API payload into display-ready ledger entries. */
export function buildNewsNotifications(
  alerts: readonly WatchedNewsAlert[],
  events: readonly WatchedNewsEvent[],
): NewsNotification[] {
  const out: NewsNotification[] = [];

  for (const alert of alerts) {
    if (!alert?.id || !alert?.headline) continue;
    const body = [
      levelLabel(alert.alertLevel),
      alert.source,
      alert.ticker,
      typeof alert.importance === 'number' ? `score ${alert.importance}` : null,
    ]
      .filter(Boolean)
      .join(' · ');
    out.push({ id: `news:${alert.id}`, title: alert.headline, body, url: sourceUrl(alert.url) });
  }

  for (const event of events) {
    if (!event?.id || !event?.title) continue;
    const minutes = typeof event.minutesUntil === 'number' ? event.minutesUntil : null;
    if (minutes !== null && minutes > EVENT_NOTIFY_HORIZON_MINUTES) continue;
    const body = [
      `High-impact release · ${event.country || 'GLOBAL'}`,
      minutes !== null ? `in ${minutes}m` : 'upcoming',
      event.forecast ? `forecast ${event.forecast}` : null,
      event.previous ? `prev ${event.previous}` : null,
    ]
      .filter(Boolean)
      .join(' · ');
    out.push({ id: `news-event:${event.id}`, title: event.title, body });
  }

  return out;
}

/**
 * Diff the current payload against the seen set.
 *
 * `seed` updates the seen set and returns NO notifications (booting must not
 * replay history). Otherwise only ids that were not seen before are returned.
 */
export function diffNewsNotifications(
  current: readonly NewsNotification[],
  seen: ReadonlySet<string>,
  opts: { seed: boolean },
): { notifications: NewsNotification[]; next: Set<string> } {
  const next = new Set(seen);
  const fresh: NewsNotification[] = [];

  for (const item of current) {
    if (next.has(item.id)) continue;
    next.add(item.id);
    fresh.push(item);
  }

  const bounded = Array.from(next).slice(-MAX_SEEN_NEWS_NOTIFICATIONS);
  return {
    notifications: opts.seed ? [] : fresh,
    next: new Set(bounded),
  };
}
