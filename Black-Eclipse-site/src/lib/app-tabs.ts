// ── AppTab — the ONE tab vocabulary ─────────────────────────────────────────
// The SPA shell is tabbed (no router). The set of tabs was declared twice: once
// in `components/layout/sidebar.tsx` (the shell's source of truth) and once as a
// mirror in `lib/search/types.ts`. Nothing kept them equal, so adding a tab to
// one silently narrowed the other — and `lib/general-prefs.ts` imports the mirror
// for its boot-screen allowlist, so a drift would drop a persisted start tab.
//
// This module is the single declaration. Both consumers re-export it, so the two
// can no longer disagree (the `app-tabs.test.ts` guard also pins them equal).

export const APP_TABS = [
  'chat',
  'home',
  'news',
  'discovery',
  'heatmap',
  'chart',
  'economics',
  'portfolio',
  'journal',
  'settings',
  'alerts',
  'dashboard',
  'market-workspace',
  'investor-eye',
  'skills',
  'memory',
  'artifacts',
  'tasks',
  'pages',
  'ui-builder',
  'backtest',
  'strategy-studio',
  'research-data',
  'factor-lab',
  'ml-lab',
  'graph-studio',
  'tables',
  'overview',
  'bots',
  'code',
] as const;

export type AppTab = (typeof APP_TABS)[number];
