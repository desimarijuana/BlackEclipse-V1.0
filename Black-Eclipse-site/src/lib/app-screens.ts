// ── Rendered screen tabs — the source of truth for app surfaces ─────────────
// `app-surfaces.ts` first derived sub-tabs from the search-palette registry.
// That registry is palette-shaped and incomplete: the Memory screen renders 15
// tabs while the registry declared 8, with different labels ("Facts" vs "Memory
// Explorer", "Reviews" vs "Learning Reviews"), and Skills renders Maintenance
// with no registry entry. A QA run answered from the stale list, so the
// inventory now comes from the tab bars themselves: these arrays are imported
// by BOTH the screen components and the synced surface map. One list, no drift.

import type { AppTab } from './app-tabs';

export type MemoryTabId =
  | 'overview' | 'facts' | 'sessions' | 'review' | 'preferences' | 'settings'
  | 'maintenance';

export type SkillsTabId =
  | 'library' | 'start' | 'project' | 'bundles' | 'learn' | 'learning'
  | 'journey' | 'maintenance' | 'evaluation' | 'activity' | 'experiments';

export interface ScreenTabDef<Id extends string = string> {
  /** The screen's internal tab id — also the canonical deep-link slug. */
  id: Id;
  /** User-visible label exactly as the tab bar renders it. */
  label: string;
  /** Legacy subroute slugs the screen still accepts. */
  aliases?: string[];
  /**
   * Reachable by deep link but not rendered in a tab bar. Used for views that
   * became first-run / empty-state content (e.g. Skills → Start Here).
   */
  hidden?: boolean;
}

/** A primary tab bar entry that groups related sub-tabs. */
export interface ScreenTabGroup<Id extends string = string> {
  id: string;
  label: string;
  /** Ordered sub-tabs. A group with one visible child renders no sub-bar. */
  tabs: Id[];
}

export interface ScreenDef<Id extends string = string> {
  id: AppTab;
  label: string;
  tabs: ScreenTabDef<Id>[];
}

/** Eclipse Memory — the rendered tab bar, in order.
 *
 * Seven tabs, each owning a related cluster of views. Previously 16 top-level
 * tabs mixed daily browsing (facts/sessions) with configuration (policies/
 * providers) and one-off operations (files/export/reset), which made the same
 * record appear twice and pushed real content below diagnostic prose. The old
 * slugs remain aliases so existing deep links keep working; the screen maps
 * them to the right internal section.
 */
export const MEMORY_TABS: ScreenTabDef<MemoryTabId>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'facts', label: 'Facts', aliases: ['memories', 'explorer', 'lifecycle'] },
  { id: 'sessions', label: 'Sessions', aliases: ['history', 'search', 'session-search'] },
  { id: 'review', label: 'Review', aliases: ['suggestions', 'reviews', 'learning'] },
  { id: 'preferences', label: 'Preferences', aliases: ['prefs', 'profile', 'context'] },
  { id: 'settings', label: 'Settings', aliases: ['profiles', 'providers', 'policies'] },
  { id: 'maintenance', label: 'Maintenance', aliases: ['activity', 'files', 'health', 'health-export', 'diagnostics'] },
];

/**
 * Skills — every view, in declaration order. `SKILLS_GROUPS` is what the
 * primary tab bar renders; this array stays the deep-link and surface-map
 * inventory, so collapsing the bar never orphans a link.
 */
export const SKILLS_TABS: ScreenTabDef<SkillsTabId>[] = [
  { id: 'library', label: 'Skills Library' },
  // Kept reachable (`/?tab=skills&sub=skills.start`) but no longer a tab: its
  // content is the Library's first-run state.
  { id: 'start', label: 'Start Here', hidden: true },
  { id: 'learn', label: 'Learn a Skill' },
  { id: 'learning', label: 'Learning Queue' },
  { id: 'journey', label: 'Learning Journey' },
  { id: 'project', label: 'Project Skills' },
  { id: 'bundles', label: 'Bundles' },
  { id: 'evaluation', label: 'Evaluation Center' },
  { id: 'activity', label: 'Execution Activity' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'experiments', label: 'Experiments' },
];

/** Skills — the five primary destinations. */
export const SKILLS_GROUPS: ScreenTabGroup<SkillsTabId>[] = [
  { id: 'library', label: 'Library', tabs: ['library', 'start'] },
  { id: 'learning', label: 'Learning', tabs: ['learn', 'learning'] },
  { id: 'journey', label: 'Journey', tabs: ['journey'] },
  { id: 'collections', label: 'Collections', tabs: ['project', 'bundles'] },
  {
    id: 'operations',
    label: 'Operations',
    tabs: ['evaluation', 'activity', 'maintenance', 'experiments'],
  },
];

/** Screens whose rendered tab bar is the inventory authority. */
export const APP_SCREENS: ScreenDef[] = [
  { id: 'memory', label: 'Eclipse Memory', tabs: MEMORY_TABS },
  { id: 'skills', label: 'Skills', tabs: SKILLS_TABS },
];

/** Resolve a deep-link slug (or a legacy alias) to its tab definition. */
export function screenTab<Id extends string>(
  defs: ScreenTabDef<Id>[],
  slug: string | null | undefined,
): ScreenTabDef<Id> | undefined {
  if (!slug) return undefined;
  return defs.find((tab) => tab.id === slug || (tab.aliases ?? []).includes(slug));
}

/** The group that owns a tab id (falls back to the first group). */
export function screenGroupForTab<Id extends string>(
  groups: ScreenTabGroup<Id>[],
  tab: Id,
): ScreenTabGroup<Id> {
  return groups.find((group) => group.tabs.includes(tab)) ?? groups[0];
}

/** Sub-tabs a group renders, excluding hidden/deep-link-only views. */
export function visibleGroupTabs<Id extends string>(
  group: ScreenTabGroup<Id>,
  defs: ScreenTabDef<Id>[],
): ScreenTabDef<Id>[] {
  const hidden = new Set(defs.filter((def) => def.hidden).map((def) => def.id));
  return group.tabs
    .filter((id) => !hidden.has(id))
    .map((id) => defs.find((def) => def.id === id))
    .filter((def): def is ScreenTabDef<Id> => Boolean(def));
}
