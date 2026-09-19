'use client';

// ── User market preference ──────────────────────────────────────────────────
// One persisted "which market is the user looking at" value, shared across the
// market surfaces (Screener, Market Bubbles). Before this, each screen kept its
// own default — Market Bubbles always opened on CRYPTO regardless of what the
// user picked elsewhere — so the choice did not carry between pages.
//
// Resolution order for the initial value:
//   1. the last market the user explicitly selected (this store),
//   2. the default market saved in Settings (`app_preferences.defaultMarket`,
//      passed in by the caller when known),
//   3. the browser-locale guess (e.g. en-PK → PK),
//   4. 'US' as the final fallback.

import { HEATMAP_MARKETS } from '@/lib/heatmap';

const STORAGE_KEY = 'eclipse_user_market';

/** Market ids the market surfaces actually support (heatmap universe). */
export function isKnownMarket(id: string): boolean {
  return HEATMAP_MARKETS.some((m) => m.id === id.toUpperCase());
}

/** Country/region from the browser locale (en-PK → PK), when supported. */
export function localeDefaultMarket(): string | null {
  if (typeof navigator === 'undefined') return null;
  try {
    const region = (navigator.language || '').split('-')[1]?.toUpperCase();
    if (region && isKnownMarket(region)) return region;
  } catch {
    /* ignore */
  }
  return null;
}

/** The user's last explicit market choice, or null when none is stored. */
export function getUserMarket(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v && isKnownMarket(v)) return v.toUpperCase();
  } catch {
    /* ignore */
  }
  return null;
}

/** Remember the user's explicit market choice for all market surfaces. */
export function setUserMarket(market: string): void {
  if (typeof window === 'undefined') return;
  const id = market.toUpperCase();
  if (!isKnownMarket(id)) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

/**
 * Resolve the market a surface should open on, in precedence order. `preferred`
 * is an explicit hint (e.g. a deep-link or the Settings default market).
 */
export function resolveUserMarket(preferred?: string | null): string {
  if (preferred && isKnownMarket(preferred)) return preferred.toUpperCase();
  const stored = getUserMarket();
  if (stored) return stored;
  const locale = localeDefaultMarket();
  if (locale) return locale;
  return 'US';
}
