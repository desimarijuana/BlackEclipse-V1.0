// ── Economic event resolution ────────────────────────────────────────────────
// Fetches the live economic calendar once and matches queries like "next NFP",
// "CPI this month", "FOMC" to actual upcoming releases. Deterministic — no LLM.
// The calendar is server-cached (10-min SWR), so this is a single fetch.

import type { SearchEntity } from './types';

export interface CalendarEvent {
  id: string;
  date: string;
  country: string;
  title: string;
  importance: 'high' | 'medium' | 'low';
  actual: string | null;
  forecast: string | null;
  previous: string | null;
}

let eventsCache: CalendarEvent[] | null = null;
let loading: Promise<void> | null = null;

/** Test-only: inject a calendar snapshot without a network fetch. */
export function __setEventsForTest(events: CalendarEvent[] | null): void {
  eventsCache = events;
}

/** Fetch the calendar once (idempotent). */
export function loadCalendar(): Promise<void> {
  if (eventsCache) return Promise.resolve();
  if (loading) return loading;
  loading = (async () => {
    try {
      const res = await fetch('/api/economics/calendar', { cache: 'no-store' });
      if (!res.ok) throw new Error(`calendar ${res.status}`);
      const d = await res.json();
      eventsCache = Array.isArray(d.events) ? d.events : [];
    } catch {
      eventsCache = [];
    } finally {
      loading = null;
    }
  })();
  return loading;
}

export function isCalendarLoaded(): boolean {
  return eventsCache !== null;
}

/** Keyword → event matcher. Returns the best upcoming event for a query. */
const EVENT_KEYWORDS: { key: string; match: (title: string) => boolean }[] = [
  { key: 'nfp', match: (t) => /nonfarm|non-farm|payroll|nfp/i.test(t) },
  { key: 'cpi', match: (t) => /cpi|consumer price/i.test(t) },
  { key: 'gdp', match: (t) => /gdp|gross domestic/i.test(t) },
  { key: 'fomc', match: (t) => /fomc|federal reserve|interest rate decision/i.test(t) },
  { key: 'pmi', match: (t) => /pmi|ism|purchasing managers/i.test(t) },
  { key: 'unemployment', match: (t) => /unemployment|jobless/i.test(t) },
  { key: 'ecb', match: (t) => /ecb|european central bank/i.test(t) },
  { key: 'boe', match: (t) => /boe|bank of england/i.test(t) },
  { key: 'boj', match: (t) => /boj|bank of japan/i.test(t) },
];

function matchKey(query: string): string | null {
  const q = query.toLowerCase();
  for (const { key, match } of EVENT_KEYWORDS) {
    if (q.includes(key) || match(query)) return key;
  }
  return null;
}

/** Resolve a query to an upcoming calendar event entity, if any. */
export function resolveEvent(query: string): SearchEntity | null {
  if (!eventsCache || eventsCache.length === 0) return null;
  const key = matchKey(query);
  if (!key) return null;

  const now = Date.now();
  const upcoming = eventsCache
    .filter((e) => Date.parse(e.date) >= now - 24 * 3600 * 1000)
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));

  const match = upcoming.find((e) => EVENT_KEYWORDS.find((k) => k.key === key)?.match(e.title));
  if (!match) return null;

  const when = new Date(match.date);
  const day = when.toUTCString().slice(0, 16);
  const time = when.toISOString().slice(11, 16);

  return {
    id: `event-${match.id}`,
    kind: 'event',
    title: match.title,
    keywords: [key, match.title.toLowerCase()],
    icon: 'globe',
    destination: { tab: 'economics', subroute: 'economics.calendar', params: { focus: key.toUpperCase() } },
    subtitle: `${day} ${time} UTC · ${match.country} · ${match.importance}`,
    rankBoost: 1.2,
  };
}
