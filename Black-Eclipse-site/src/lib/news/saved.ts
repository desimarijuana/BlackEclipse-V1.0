// ─── Saved (bookmarked) news ────────────────────────────────────────────────
// Bookmarks used to persist only IDs, which meant the Saved view could only
// show whatever happened to be on the current feed page. They now persist the
// full article snapshot so the Saved view can list, search, filter and page
// through everything the user kept. Legacy ID-only saves are migrated lazily
// when the same article next appears in the feed.

import type { NewsItem } from '@/components/screens/market-news';

export const SAVED_ITEMS_KEY = 'be_news_saved_items_v1';
const LEGACY_IDS_KEY = 'be_news_saved_ids';
export const MAX_SAVED_ITEMS = 500;

export interface SavedState {
  items: NewsItem[];
  /** IDs saved before full snapshots were stored. */
  legacyIds: string[];
}

function readArray<T>(key: string): T[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || '[]');
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function loadSaved(): SavedState {
  if (typeof window === 'undefined') return { items: [], legacyIds: [] };
  const items = readArray<NewsItem>(SAVED_ITEMS_KEY).filter(
    (item) => item && typeof item.id === 'string' && typeof item.headline === 'string',
  );
  // Once a snapshot store exists, the legacy ID list is only a migration aid.
  const known = new Set(items.map((item) => item.id));
  const legacyIds = readArray<string>(LEGACY_IDS_KEY).filter((id) => typeof id === 'string' && !known.has(id));
  return { items, legacyIds };
}

export function saveSaved(items: NewsItem[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SAVED_ITEMS_KEY, JSON.stringify(items.slice(0, MAX_SAVED_ITEMS)));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export function saveLegacyIds(ids: Iterable<string>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LEGACY_IDS_KEY, JSON.stringify([...ids]));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** Move ID-only saves into the snapshot store as their articles reach the feed. */
export function adoptLegacySaves(
  feed: NewsItem[],
  items: NewsItem[],
  legacyIds: Set<string>,
): { items: NewsItem[]; legacyIds: Set<string> } {
  const adopt = feed.filter((n) => legacyIds.has(n.id) && !items.some((s) => s.id === n.id));
  if (adopt.length === 0) return { items, legacyIds };
  const nextItems = [...items, ...adopt].slice(0, MAX_SAVED_ITEMS);
  const nextIds = new Set(legacyIds);
  adopt.forEach((n) => nextIds.delete(n.id));
  saveSaved(nextItems);
  saveLegacyIds(nextIds);
  return { items: nextItems, legacyIds: nextIds };
}
