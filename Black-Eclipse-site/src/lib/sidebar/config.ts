// ── Sidebar customization ─────────────────────────────────────────────────
// Canonical list of the SPA's primary navigation items, plus the user's
// per-item customization (order, visibility, keyboard shortcut). The sidebar
// and the Settings › Sidebar panel both read from here so they never drift.
//
// Persistence is client-side (localStorage) — deliberately presentation-layer
// only, matching the currency + search-recents conventions in this repo.

'use client';

import {
  LayoutDashboard, ChartCandlestick, ScanSearch, ChartPie, Bot,
  BookOpen, Newspaper, Orbit, Globe, Bell, ScanEye, type LucideIcon,
} from 'lucide-react';
import type { AppTab } from '@/components/layout/sidebar';

export interface SidebarSectionDef {
  /** Matches an AppTab id. */
  id: AppTab;
  label: string;
  icon: LucideIcon;
}

/** The primary navigation menu, in the shipped default order. ChatBot (the
 *  harness) leads by default, but the order is fully user-customizable. */
export const DEFAULT_SIDEBAR_SECTIONS: SidebarSectionDef[] = [
  { id: 'chat', label: 'ChatBot', icon: Bot },
  { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard },
  { id: 'investor-eye', label: 'Investor Eye', icon: ScanEye },
  { id: 'market-workspace', label: 'Chart Workspace', icon: ChartCandlestick },
  { id: 'discovery', label: 'Market Screener', icon: ScanSearch },
  { id: 'portfolio', label: 'Portfolio', icon: ChartPie },
  { id: 'journal', label: 'Journal', icon: BookOpen },
  { id: 'news', label: 'Market News', icon: Newspaper },
  { id: 'heatmap', label: 'Market Bubbles', icon: Orbit },
  { id: 'economics', label: 'Economics', icon: Globe },
  { id: 'alerts', label: 'Price Alerts', icon: Bell },
];

/** Per-item user config; id is the AppTab id. */
export interface SidebarSectionConfig {
  id: AppTab;
  enabled: boolean;
  /** Empty string = no shortcut assigned. */
  shortcut: string;
}

export interface SidebarConfig {
  sections: SidebarSectionConfig[];
}

/** Shortcut choices offered in Settings. Keyboard codes (not labels). */
export const SHORTCUT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'None' },
  ...Array.from({ length: 12 }, (_, i) => ({ value: `F${i + 1}`, label: `F${i + 1}` })),
];

export const SIDEBAR_CONFIG_KEY = 'be_sidebar_config_v1';

/** The order shipped before ChatBot was moved to the top (migration baseline). */
const LEGACY_DEFAULT_ORDER: AppTab[] = [
  'dashboard', 'market-workspace', 'chat', 'discovery', 'portfolio',
  'journal', 'news', 'heatmap', 'economics', 'alerts',
];

export function defaultSidebarConfig(): SidebarConfig {
  return {
    sections: DEFAULT_SIDEBAR_SECTIONS.map((s) => ({ id: s.id, enabled: true, shortcut: '' })),
  };
}

export function loadSidebarConfig(): SidebarConfig {
  const base = defaultSidebarConfig();
  if (typeof window === 'undefined') return base;
  try {
    const raw = localStorage.getItem(SIDEBAR_CONFIG_KEY);
    if (!raw) return base;
    const parsed = JSON.parse(raw) as Partial<SidebarConfig>;
    const incoming = parsed?.sections ?? [];

    // Reconcile with the canonical list: kept items inherit saved config,
    // brand-new tab ids are appended (enabled, no shortcut), and retired ids
    // are dropped. This keeps upgrades from losing a user's ordering.
    // One-time migration: if the saved order is exactly the LEGACY shipped
    // default (i.e. the user never customized it), adopt the new default so
    // ChatBot leads. Any genuinely customized order is preserved below.
    const incomingIds = incoming.map((s) => s.id);
    if (incomingIds.length === LEGACY_DEFAULT_ORDER.length && incomingIds.every((id, i) => id === LEGACY_DEFAULT_ORDER[i])) {
      return base;
    }

    const known = new Set<string>(DEFAULT_SIDEBAR_SECTIONS.map((d) => d.id));

    // Preserve the user's saved ORDER for known ids, carrying over their
    // enabled/shortcut settings. Retired ids are dropped.
    const merged: SidebarSectionConfig[] = [];
    for (const s of incoming) {
      if (!known.has(s.id)) continue;
      merged.push({ id: s.id, enabled: s.enabled !== false, shortcut: s.shortcut ?? '' });
    }

    // Append any canonical section not present yet (upgrade path) at the end.
    const present = new Set(merged.map((s) => s.id));
    for (const def of DEFAULT_SIDEBAR_SECTIONS) {
      if (!present.has(def.id)) {
        merged.push({ id: def.id, enabled: true, shortcut: '' });
      }
    }
    return { sections: merged };
  } catch {
    return base;
  }
}

export function saveSidebarConfig(cfg: SidebarConfig) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SIDEBAR_CONFIG_KEY, JSON.stringify(cfg));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export function resetSidebarConfig() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(SIDEBAR_CONFIG_KEY);
  } catch {
    /* ignore */
  }
}

/** Build the id → config lookup the sidebar consumes. */
export function configMap(cfg: SidebarConfig): Map<string, SidebarSectionConfig> {
  return new Map(cfg.sections.map((s) => [s.id, s]));
}

/** First section (in the user's order) with a matching key code. */
export function shortcutTab(cfg: SidebarConfig, code: string): AppTab | null {
  const hit = cfg.sections.find((s) => s.enabled && s.shortcut && s.shortcut === code);
  return hit ? hit.id : null;
}
