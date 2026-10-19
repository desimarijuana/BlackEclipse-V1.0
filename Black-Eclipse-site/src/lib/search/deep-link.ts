// ── Deep links ──────────────────────────────────────────────────────────────
// Black Eclipse is a tabbed SPA (no router), so a "page" has no URL of its own.
// This module gives every Destination a real, shareable href so page launchers
// can be genuine anchors — enabling Ctrl/Cmd-click, middle-click and "open in
// new tab", plus refresh/share. The shell boots from the same params on load.
//
// URL shape: `/?tab=<tab>&sub=<subroute>&<param>=<value>…`
//   `tab` and `sub` are reserved; every other key becomes a Destination param.
// Back-compat: a bare `?symbol=AAPL` (the pre-existing chart deep link) boots
// the chart tab.

import type { AppTab, Destination } from './types';

// Every tab id the SPA shell exposes. Declared as an EXHAUSTIVE `Record<AppTab,
// true>` so growing the `AppTab` union without listing the tab here is a
// COMPILE error — a hand-maintained array is how `graph-studio` was silently
// left out, which made `?tab=graph-studio` (and a "history" boot tab) fall back
// to ChatBot. Order is the declaration order.
const ALL_TABS: Record<AppTab, true> = {
  chat: true,
  news: true,
  discovery: true,
  heatmap: true,
  chart: true,
  economics: true,
  portfolio: true,
  journal: true,
  settings: true,
  alerts: true,
  dashboard: true,
  'market-workspace': true,
  'investor-eye': true,
  skills: true,
  memory: true,
  artifacts: true,
  tasks: true,
  pages: true,
  'ui-builder': true,
  sdk: true,
  backtest: true,
  'research-data': true,
  'factor-lab': true,
  'ml-lab': true,
  'graph-studio': true,
  bots: true,
};

export const APP_TABS = Object.keys(ALL_TABS) as readonly AppTab[];

/** Query keys consumed by the link format itself (never treated as params). */
const RESERVED = new Set(['tab', 'sub']);

/** Serialize a Destination into a query string (no leading `?`). */
export function destinationToQuery(dest: Destination): string {
  const sp = new URLSearchParams();
  sp.set('tab', dest.tab);
  if (dest.subroute) sp.set('sub', dest.subroute);
  for (const [k, v] of Object.entries(dest.params ?? {})) {
    if (v != null && v !== '') sp.set(k, v);
  }
  return sp.toString();
}

/** Build a full href for a Destination. Relative by default, so it works from
 *  any origin and in tests without `window`. */
export function destinationToHref(dest: Destination, base = '/'): string {
  return `${base}?${destinationToQuery(dest)}`;
}

/** Shorthand: the href for a top-level tab (optionally with params). */
export function hrefForTab(tab: AppTab, params?: Record<string, string>): string {
  return destinationToHref({ tab, ...(params ? { params } : {}) });
}

/**
 * Parse a URL's search string back into a Destination. Returns null when there
 * is nothing routable. A bare `?symbol=…` (no `tab`) is treated as the chart
 * deep link for backward compatibility.
 */
export function parseDeepLink(search: string): Destination | null {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  if (!raw) return null;
  let sp: URLSearchParams;
  try {
    sp = new URLSearchParams(raw);
  } catch {
    return null;
  }

  const params: Record<string, string> = {};
  let tabParam: string | null = null;
  let subroute: string | undefined;
  for (const [k, v] of sp.entries()) {
    if (k === 'tab') { tabParam = v; continue; }
    if (k === 'sub') { subroute = v || undefined; continue; }
    if (RESERVED.has(k)) continue;
    if (v !== '') params[k] = v;
  }

  const hasParams = Object.keys(params).length > 0;
  if (tabParam && (APP_TABS as readonly string[]).includes(tabParam)) {
    return {
      tab: tabParam as AppTab,
      ...(subroute ? { subroute } : {}),
      ...(hasParams ? { params } : {}),
    };
  }

  // Back-compat: `/?symbol=AAPL` boots the chart tab.
  if (params.symbol) {
    return { tab: 'chart', params };
  }
  return null;
}
