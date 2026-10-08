// ── Navigation label mapping ────────────────────────────────────────────────
// The sidebar config carries stable English labels as a fallback, but the UI
// should render the translated name. This maps each AppTab id to its
// translation key so both the sidebar and the shortcut dialog stay in sync.

import type { TranslationKey } from './types';

export type NavTabId =
  | 'chat' | 'dashboard' | 'investor-eye' | 'market-workspace' | 'discovery'
  | 'portfolio' | 'journal' | 'news' | 'heatmap' | 'economics' | 'alerts'
  | 'skills' | 'memory';

const NAV_KEY_BY_TAB: Record<NavTabId, TranslationKey> = {
  chat: 'nav.chat',
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
  memory: 'nav.memory',
};

/** Translation key for a navigation tab, or null if it is not a nav item. */
export function navLabelKey(tab: string): TranslationKey | null {
  return NAV_KEY_BY_TAB[tab as NavTabId] ?? null;
}
