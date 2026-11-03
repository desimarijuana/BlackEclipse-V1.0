// ── Navigation label mapping ────────────────────────────────────────────────
// The sidebar config carries stable English labels as a fallback, but the UI
// should render the translated name. This maps each AppTab id to its
// translation key so both the sidebar and the shortcut dialog stay in sync.

import type { TranslationKey } from './types';

export type NavTabId =
  | 'chat' | 'home' | 'dashboard' | 'investor-eye' | 'market-workspace' | 'discovery'
  | 'portfolio' | 'journal' | 'news' | 'heatmap' | 'economics' | 'alerts'
  | 'skills' | 'sdk' | 'memory' | 'artifacts' | 'tasks' | 'pages' | 'ui-builder' | 'backtest' | 'strategy-studio' | 'research-data' | 'graph-studio' | 'tables' | 'overview'
  | 'bots';

const NAV_KEY_BY_TAB: Record<NavTabId, TranslationKey> = {
  chat: 'nav.chat',
  home: 'nav.home',
  dashboard: 'nav.dashboard',
  'investor-eye': 'nav.investorEye',
  'market-workspace': 'nav.marketWorkspace',
  discovery: 'nav.discovery',
  portfolio: 'nav.portfolio',
  journal: 'nav.journal',
  news: 'nav.news',
  heatmap: 'nav.heatmap',
  economics: 'nav.economics',
  alerts: 'nav.alerts',
  skills: 'nav.skills',
  sdk: 'nav.sdk',
  memory: 'nav.memory',
  artifacts: 'nav.artifacts',
  tasks: 'nav.tasks',
  pages: 'nav.pages',
  'ui-builder': 'nav.uiBuilder',
  backtest: 'nav.backtest',
  'strategy-studio': 'nav.strategyStudio',
  'research-data': 'nav.researchData',
  'graph-studio': 'nav.graphStudio',
  tables: 'nav.tables',
  overview: 'nav.overview',
  bots: 'nav.bots',
};

/** Translation key for a navigation tab, or null if it is not a nav item. */
export function navLabelKey(tab: string): TranslationKey | null {
  return NAV_KEY_BY_TAB[tab as NavTabId] ?? null;
}
