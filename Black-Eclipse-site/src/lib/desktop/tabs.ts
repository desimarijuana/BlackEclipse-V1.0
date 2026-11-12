// ── Desktop tab strip state ─────────────────────────────────────────────────
// The native shell adds a browser-style tab strip over the SPA's top-level
// pages. Tabs are INSTANCES, not a de-duplicated set of pages: `+` can create a
// second Chat (or Portfolio, …) tab, and navigating inside a tab moves that tab
// to the page you chose. This module owns the pure open/close/reorder rules and
// the localStorage hand-off so the shell restores the same tabs on relaunch.
// React lives in `components/layout/desktop-tab-bar.tsx`; keep this file
// framework-free so it can be tested without a DOM.

import { APP_TABS, type AppTab } from '@/lib/app-tabs';
import { isNavGroup, type NavGroup } from '@/lib/sidebar/config';

const STORAGE_KEY = 'be_desktop_tabs_v2';
/** Pre-instances format: an array of page ids only. Read once on upgrade. */
const LEGACY_KEY = 'be_desktop_tabs_v1';
const TAB_SET = new Set<string>(APP_TABS);

export interface DesktopTab {
  /** Stable tab identity; survives page changes and relaunches. */
  id: string;
  page: AppTab;
  /**
   * The sidebar MENU MODE this tab was last showing (Terminal / Agentic / Bots /
   * Graph). Desktop tabs are in-page instances inside one browser shell, so the
   * sidebar's session-scoped mode would otherwise be shared by every tab —
   * switching to a Bots tab would drag a Command Center tab out of Terminal.
   * The strip records the mode here on switch and restores it on return.
   * Absent on upgraded stores; the shell then seeds it with the current mode.
   */
  mode?: NavGroup;
}

let seq = 0;

function newId(): string {
  seq += 1;
  return `dt_${Date.now().toString(36)}_${seq}`;
}

export function createTab(page: AppTab, id?: string, mode?: NavGroup): DesktopTab {
  return mode ? { id: id ?? newId(), page, mode } : { id: id ?? newId(), page };
}

/** Record the sidebar mode a tab is showing, so returning to it restores that mode. */
export function setTabMode(tabs: DesktopTab[], id: string, mode: NavGroup): DesktopTab[] {
  const index = tabs.findIndex((tab) => tab.id === id);
  if (index === -1 || tabs[index].mode === mode) return tabs;
  const next = [...tabs];
  next[index] = { ...next[index], mode };
  return next;
}

export function isAppTab(value: unknown): value is AppTab {
  return typeof value === 'string' && TAB_SET.has(value);
}

/** Append a tab instance (duplicates of a page are allowed). A new tab starts
 *  in the mode the user is currently looking at. */
export function appendTab(
  tabs: DesktopTab[],
  page: AppTab,
  mode?: NavGroup,
): { tabs: DesktopTab[]; tab: DesktopTab } {
  const tab = createTab(page, undefined, mode);
  return { tabs: [...tabs, tab], tab };
}

/** Move the tab with `id` to the index currently occupied by `before`. */
export function moveTab(tabs: DesktopTab[], id: string, before: string): DesktopTab[] {
  const from = tabs.findIndex((tab) => tab.id === id);
  const to = tabs.findIndex((tab) => tab.id === before);
  if (from === -1 || to === -1 || from === to) return tabs;
  const next = [...tabs];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/**
 * Close `id`. The last tab is never removed (there is always a page in front of
 * the user). Closing the active tab activates the neighbour to its right, or
 * the new last tab when it was the right-most one.
 */
export function removeTab(
  tabs: DesktopTab[],
  id: string,
  activeId: string,
): { tabs: DesktopTab[]; activeId: string } {
  const index = tabs.findIndex((tab) => tab.id === id);
  if (index === -1 || tabs.length <= 1) return { tabs, activeId };

  const next = tabs.filter((tab) => tab.id !== id);
  if (id !== activeId) return { tabs: next, activeId };
  return { tabs: next, activeId: next[Math.min(index, next.length - 1)].id };
}

/** Point the active tab at a page after in-app navigation. */
export function setTabPage(tabs: DesktopTab[], id: string, page: AppTab): DesktopTab[] {
  const index = tabs.findIndex((tab) => tab.id === id);
  if (index === -1 || tabs[index].page === page) return tabs;
  const next = [...tabs];
  next[index] = { ...next[index], page };
  return next;
}

/** Move the tab with `id` one slot left (`delta < 0`) or right (`delta > 0`).
 *  Returns the same array at the edges. */
export function moveTabBy(tabs: DesktopTab[], id: string, delta: number): DesktopTab[] {
  const from = tabs.findIndex((tab) => tab.id === id);
  if (from === -1 || delta === 0) return tabs;
  const to = Math.min(tabs.length - 1, Math.max(0, from + delta));
  if (to === from) return tabs;
  const next = [...tabs];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/** Move the tab with `id` to the first or last slot. */
export function moveTabToEdge(tabs: DesktopTab[], id: string, edge: 'first' | 'last'): DesktopTab[] {
  return moveTabBy(tabs, id, edge === 'first' ? -tabs.length : tabs.length);
}

/** Recover stored tabs, dropping malformed entries and duplicate ids. */
export function parseStoredTabs(raw: string | null): DesktopTab[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    const out: DesktopTab[] = [];
    for (const item of parsed) {
      // Current shape: { id, page }. Legacy shape: a bare page id.
      const candidate = typeof item === 'string' ? { id: newId(), page: item } : item;
      if (!candidate || typeof candidate !== 'object') continue;
      const { id, page, mode } = candidate as { id?: unknown; page?: unknown; mode?: unknown };
      if (!isAppTab(page)) continue;
      const tabId = typeof id === 'string' && id.trim() ? id : newId();
      if (seen.has(tabId)) continue;
      seen.add(tabId);
      out.push(isNavGroup(mode) ? { id: tabId, page, mode } : { id: tabId, page });
    }
    return out;
  } catch {
    return [];
  }
}

export function readStoredTabs(): DesktopTab[] {
  if (typeof window === 'undefined') return [];
  try {
    const current = window.localStorage.getItem(STORAGE_KEY);
    if (current) return parseStoredTabs(current);
    const legacy = window.localStorage.getItem(LEGACY_KEY);
    const migrated = parseStoredTabs(legacy);
    if (migrated.length > 0) saveStoredTabs(migrated);
    return migrated;
  } catch {
    return [];
  }
}

export function saveStoredTabs(tabs: DesktopTab[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  } catch {
    // Quota / private mode: the strip still works for this session.
  }
}
