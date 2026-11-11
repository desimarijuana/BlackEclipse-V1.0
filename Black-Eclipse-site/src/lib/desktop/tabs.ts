// ── Desktop tab strip state ─────────────────────────────────────────────────
// The native shell adds a browser-style tab strip over the SPA's top-level
// pages. This module owns the pure open/close rules + the localStorage
// hand-off so the shell restores the same pages on relaunch. React lives in
// `components/layout/desktop-tab-bar.tsx`; keep this file framework-free so it
// can be tested without a DOM.

import { APP_TABS, type AppTab } from '@/lib/app-tabs';

const STORAGE_KEY = 'be_desktop_tabs_v1';
const TAB_SET = new Set<string>(APP_TABS);

export function isAppTab(value: unknown): value is AppTab {
  return typeof value === 'string' && TAB_SET.has(value);
}

/** Append a page tab unless it is already open. Order is the open order. */
export function addTab(tabs: AppTab[], tab: AppTab): AppTab[] {
  return tabs.includes(tab) ? tabs : [...tabs, tab];
}

/**
 * Close `tab`. The last tab is never removed (there is always a page in front
 * of the user). Closing the active tab activates the neighbour to its right,
 * or the new last tab when it was the right-most one.
 */
export function removeTab(
  tabs: AppTab[],
  tab: AppTab,
  activeTab: AppTab,
): { tabs: AppTab[]; activeTab: AppTab } {
  const index = tabs.indexOf(tab);
  if (index === -1 || tabs.length <= 1) return { tabs, activeTab };

  const next = tabs.filter((id) => id !== tab);
  if (tab !== activeTab) return { tabs: next, activeTab };
  return { tabs: next, activeTab: next[Math.min(index, next.length - 1)] };
}

/** Move `tab` to the index currently occupied by `before` (drag reorder).
 *  Returns the same array when either tab is missing or the move is a no-op. */
export function moveTab(tabs: AppTab[], tab: AppTab, before: AppTab): AppTab[] {
  const from = tabs.indexOf(tab);
  const to = tabs.indexOf(before);
  if (from === -1 || to === -1 || from === to) return tabs;
  const next = [...tabs];
  next.splice(from, 1);
  next.splice(to, 0, tab);
  return next;
}

/** Recover a stored tab list, dropping anything no longer in `APP_TABS`. */
export function parseStoredTabs(raw: string | null): AppTab[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isAppTab);
  } catch {
    return [];
  }
}

export function readStoredTabs(): AppTab[] {
  if (typeof window === 'undefined') return [];
  try {
    return parseStoredTabs(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return [];
  }
}

export function saveStoredTabs(tabs: AppTab[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  } catch {
    // Quota / private mode: the strip still works for this session.
  }
}
