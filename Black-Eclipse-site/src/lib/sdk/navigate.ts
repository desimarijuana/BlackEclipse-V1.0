// ── Local app-shell navigation ───────────────────────────────────────────────
// Builds the shell's deep link and applies it through the existing popstate
// path. No React import, so both `eclipseSdk.app.open` and the SSE sync can use
// it without a store/client cycle.

import type { AppNavigateTarget } from './app-shell-types';

/** Pending board selection, consumed when DashboardScreen mounts/loads. */
export const PENDING_DASHBOARD_KEY = 'be_open_dashboard_v1';

export function navigateTo(target: AppNavigateTarget): void {
  if (typeof window === 'undefined') return;

  if (target.dashboardId) {
    try {
      window.localStorage.setItem(PENDING_DASHBOARD_KEY, target.dashboardId);
    } catch {
      /* storage unavailable — the live event below still applies if mounted */
    }
    window.dispatchEvent(new CustomEvent('eclipse:open-dashboard', {
      detail: { dashboardId: target.dashboardId },
    }));
  }

  const sp = new URLSearchParams();
  const tab = target.page ? 'pages' : target.tab;
  sp.set('tab', tab);
  if (target.subroute) sp.set('sub', target.subroute);
  if (target.page) sp.set('page', target.page);
  for (const [key, value] of Object.entries(target.params ?? {})) {
    if (key !== 'tab' && key !== 'sub' && value) sp.set(key, value);
  }
  const query = sp.toString();
  if (window.location.search.slice(1) !== query) {
    try {
      window.history.pushState(null, '', `${window.location.pathname}?${query}`);
    } catch {
      /* history unavailable — the popstate below still switches the tab */
    }
  }
  window.dispatchEvent(new PopStateEvent('popstate'));
}
