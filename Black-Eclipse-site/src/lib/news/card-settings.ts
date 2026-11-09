// ─── News card customization ────────────────────────────────────────────────
// User-tunable card appearance, persisted per-browser in localStorage. Kept
// out of the screen component so `market-news.tsx` stays under the size budget.

export interface CardSettings {
  columns: 1 | 2 | 3;            // grid layout
  density: 'compact' | 'cozy';   // card padding + font scale
  showSummary: boolean;
  summaryLines: 2 | 3 | 4 | 0;   // 0 = unlimited
  showBadges: boolean;           // source/category/ticker row
  showSentiment: boolean;        // sentiment pill + swing estimate
  showButtons: boolean;          // footer action row
  showTimestamp: boolean;
  glow: boolean;                 // ambient sentiment glow
  perPage: number;               // cards per page (typed, 1…MAX_PER_PAGE)
  sort: 'newest' | 'oldest' | 'importance'; // list order
  autoRefresh: boolean;          // poll for new articles in the background
  refreshSec: 30 | 60 | 120;     // poll interval
}

/** The news API clamps `limit` to 200; the UI must agree. */
export const MIN_PER_PAGE = 1;
export const MAX_PER_PAGE = 200;

/** Floor/ceil-honest clamp for a typed or persisted page size. */
export function clampPerPage(value: unknown): number {
  const n = Math.floor(Number(value));
  if (!Number.isFinite(n)) return DEFAULT_CARD_SETTINGS.perPage;
  return Math.min(MAX_PER_PAGE, Math.max(MIN_PER_PAGE, n));
}

export const DEFAULT_CARD_SETTINGS: CardSettings = {
  columns: 1,
  density: 'cozy',
  showSummary: true,
  summaryLines: 3,
  showBadges: true,
  showSentiment: true,
  showButtons: true,
  showTimestamp: true,
  glow: true,
  perPage: 10,
  // High-level stories are part of this list, so the default order leads with
  // the most market-moving story. "newest" remains available in Customize.
  sort: 'importance',
  autoRefresh: true,
  refreshSec: 60,
};

export const CARD_SETTINGS_KEY = 'be_news_card_settings';
const FEED_ORDER_MIGRATION_KEY = 'be_news_feed_order_v2';

export function loadCardSettings(): CardSettings {
  if (typeof window === 'undefined') return DEFAULT_CARD_SETTINGS;
  try {
    const raw = window.localStorage.getItem(CARD_SETTINGS_KEY);
    const parsed: CardSettings = raw
      ? { ...DEFAULT_CARD_SETTINGS, ...JSON.parse(raw) }
      : { ...DEFAULT_CARD_SETTINGS };
    // A previously saved value (or a hand-edited localStorage entry) may sit
    // outside the API's accepted range; normalize it before it reaches fetch.
    parsed.perPage = clampPerPage(parsed.perPage);
    // One-time move for existing users: the high-alert stories used to be a
    // separate band; they now live in the main feed ranked most-critical first.
    // A later manual switch back to "newest" is respected.
    if (!window.localStorage.getItem(FEED_ORDER_MIGRATION_KEY)) {
      if (parsed.sort === 'newest') parsed.sort = 'importance';
      window.localStorage.setItem(FEED_ORDER_MIGRATION_KEY, '1');
      window.localStorage.setItem(CARD_SETTINGS_KEY, JSON.stringify(parsed));
    }
    return parsed;
  } catch {
    return DEFAULT_CARD_SETTINGS;
  }
}

export function saveCardSettings(settings: CardSettings): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CARD_SETTINGS_KEY, JSON.stringify({
      ...settings,
      perPage: clampPerPage(settings.perPage),
    }));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export function clearCardSettings(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(CARD_SETTINGS_KEY);
  } catch {
    /* ignore */
  }
}
