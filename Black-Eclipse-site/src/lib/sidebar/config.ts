// ── Sidebar customization ─────────────────────────────────────────────────
// Canonical list of the SPA's primary navigation items, plus the user's
// per-item customization (order, visibility, keyboard shortcut). The sidebar
// and the Settings › Sidebar panel both read from here so they never drift.
//
// Persistence is client-side (localStorage) — deliberately presentation-layer
// only, matching the currency + search-recents conventions in this repo.

'use client';

import {
  LayoutDashboard, Grid2x2, Bot, ChartCandlestick, Briefcase,
  BookOpen, Newspaper, Orbit, Globe, Bell, type LucideIcon,
} from 'lucide-react';
import type { AppTab } from '@/components/layout/sidebar';

export interface SidebarSectionDef {
  /** Matches an AppTab id. */
  id: AppTab;
  label: string;
  icon: LucideIcon;
}

/** The primary navigation menu, in the shipped default order. */
export const DEFAULT_SIDEBAR_SECTIONS: SidebarSectionDef[] = [
  { id: 'chat', label: 'ChatBot', icon: Bot },
  { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard },
  { id: 'market-workspace', label: 'Market Workspace', icon: Grid2x2 },
  { id: 'discovery', label: 'Market Screener', icon: ChartCandlestick },
  { id: 'portfolio', label: 'Portfolio', icon: Briefcase },
  { id: 'journal', label: 'Journal', icon: BookOpen },
  { id: 'news', label: 'Market News', icon: Newspaper },
  { id: 'heatmap', label: 'Market Bubbles', icon: Orbit },
  { id: 'economics', label: 'Economics', icon: Globe },
  { id: 'alerts', label: 'Price Alerts', icon: Bell },
];

/**
 * Always-first navigation items, in this order. ChatBot is the harness and
 * Command Center the terminal home, so they are pinned to the top and cannot be
 * reordered or hidden — the rest of the menu is user-customizable below them.
 */
export const PINNED_SIDEBAR_IDS: AppTab[] = ['chat', 'dashboard'];

/** Is this nav item locked to its position (unmovable / untoggleable)? */
export function isPinnedSection(id: AppTab): boolean {
  return PINNED_SIDEBAR_IDS.includes(id);
}

/**
 * Force the pinned items to the front in their canonical order, keep them
 * enabled, and append everything else in the given order. Applied after every
 * load/move so pinned items can never drift — even from a stale saved config.
 */
export function normalizeSidebarConfig(cfg: SidebarConfig): SidebarConfig {
  const byId = new Map(cfg.sections.map((s) => [s.id, s]));
  const pinned: SidebarSectionConfig[] = PINNED_SIDEBAR_IDS
    .filter((id) => DEFAULT_SIDEBAR_SECTIONS.some((d) => d.id === id))
    .map((id) => ({ id, enabled: true, shortcut: byId.get(id)?.shortcut ?? '' }));
  const pinnedSet = new Set<AppTab>(PINNED_SIDEBAR_IDS);
  const rest = cfg.sections.filter((s) => !pinnedSet.has(s.id));
  // Re-append any canonical section missing entirely (upgrade path).
  const present = new Set(cfg.sections.map((s) => s.id));
  for (const def of DEFAULT_SIDEBAR_SECTIONS) {
    if (!present.has(def.id)) rest.push({ id: def.id, enabled: true, shortcut: '' });
  }
  return { sections: [...pinned, ...rest] };
}

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
    const saved = new Map(incoming.map((s) => [s.id, s]));
    const merged: SidebarSectionConfig[] = [];
    for (const def of DEFAULT_SIDEBAR_SECTIONS) {
      const s = saved.get(def.id);
      merged.push({ id: def.id, enabled: s ? s.enabled !== false : true, shortcut: s?.shortcut ?? '' });
    }
    return normalizeSidebarConfig({ sections: merged });
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
