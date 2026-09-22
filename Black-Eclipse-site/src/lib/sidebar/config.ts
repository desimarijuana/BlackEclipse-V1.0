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
  BookOpen, Newspaper, Orbit, Globe, Bell, ScanEye, Sparkles, Brain, type LucideIcon,
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
  { id: 'skills', label: 'Skills', icon: Sparkles },
  { id: 'memory', label: 'Eclipse Memory', icon: Brain },
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
  shortcutVersion?: number;
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
    shortcutVersion: 2,
    // F1..F12, unique per section. (The old scheme folded every section past
    // the tenth onto F12, which collided once the list grew.)
    sections: DEFAULT_SIDEBAR_SECTIONS.map((s, index) => ({
      id: s.id,
      enabled: true,
      shortcut: index < 12 ? `F${index + 1}` : '',
    })),
  };
}

export function loadSidebarConfig(): SidebarConfig {
  const base = defaultSidebarConfig();
  if (typeof window === 'undefined') return base;
  try {
    const raw = localStorage.getItem(SIDEBAR_CONFIG_KEY);
    if (!raw) return base;
    const parsed = JSON.parse(raw) as Partial<SidebarConfig>;
    if (!Array.isArray(parsed?.sections)) return base;
    const incoming = parsed.sections.filter((section) => section && typeof section.id === 'string');
    if (incoming.length === 0) return base;
    const incomingIds = incoming.map((s) => s.id);
    const defaultOrders = [LEGACY_DEFAULT_ORDER, DEFAULT_SIDEBAR_SECTIONS.map((s) => s.id), DEFAULT_SIDEBAR_SECTIONS.filter((s) => s.id !== 'investor-eye').map((s) => s.id)];
    const untouched = incoming.every((s) => s.enabled === true && s.shortcut === '');
    const defaultOrder = defaultOrders.some((order) => incomingIds.length === order.length && incomingIds.every((id, i) => id === order[i]));
    if (parsed.shortcutVersion !== 2 && untouched && defaultOrder) return base;

    const known = new Set<string>(DEFAULT_SIDEBAR_SECTIONS.map((d) => d.id));

    // Preserve the user's saved ORDER for known ids, carrying over their
    // enabled/shortcut settings. Retired ids are dropped.
    const merged: SidebarSectionConfig[] = [];
    for (const s of incoming) {
      if (!known.has(s.id) || merged.some((item) => item.id === s.id)) continue;
      const shortcut = typeof s.shortcut === 'string' && /^(F([1-9]|1[0-2]))?$/.test(s.shortcut) ? s.shortcut : '';
      merged.push({ id: s.id, enabled: s.enabled !== false, shortcut });
    }

    // Append any canonical section not present yet (upgrade path) at the end.
    const present = new Set(merged.map((s) => s.id));
    for (const def of DEFAULT_SIDEBAR_SECTIONS) {
      if (!present.has(def.id)) {
        merged.push({ id: def.id, enabled: true, shortcut: '' });
      }
    }
    return { sections: merged, shortcutVersion: 2 };
  } catch {
    return base;
  }
}

export function saveSidebarConfig(cfg: SidebarConfig) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SIDEBAR_CONFIG_KEY, JSON.stringify({ ...cfg, shortcutVersion: 2 }));
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
