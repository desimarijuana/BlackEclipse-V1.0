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
  | 'overview' | 'memories' | 'history' | 'preferences' | 'sessions' | 'skills' | 'suggestions'
  | 'lifecycle' | 'reviews' | 'activity' | 'profile' | 'profiles' | 'providers'
  | 'files' | 'policies' | 'health';

export type SkillsTabId =
  | 'library' | 'start' | 'project' | 'bundles' | 'learn' | 'learning'
  | 'journey' | 'maintenance' | 'evaluation' | 'activity';

export interface ScreenTabDef<Id extends string = string> {
  /** The screen's internal tab id — also the canonical deep-link slug. */
  id: Id;
  /** User-visible label exactly as the tab bar renders it. */
  label: string;
  /** Legacy subroute slugs the screen still accepts. */
  aliases?: string[];
}

export interface ScreenDef<Id extends string = string> {
  id: AppTab;
  label: string;
  tabs: ScreenTabDef<Id>[];
}

/** Eclipse Memory — the rendered tab bar, in order. */
export const MEMORY_TABS: ScreenTabDef<MemoryTabId>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'memories', label: 'Facts', aliases: ['explorer'] },
  { id: 'preferences', label: 'Preferences' },
  { id: 'history', label: 'Session Search', aliases: ['search'] },
  { id: 'sessions', label: 'Sessions' },
  { id: 'skills', label: 'Skills' },
  { id: 'suggestions', label: 'Suggestions' },
  { id: 'lifecycle', label: 'Lifecycle' },
  { id: 'reviews', label: 'Reviews', aliases: ['learning'] },
  { id: 'activity', label: 'Activity' },
  { id: 'profile', label: 'Profile' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'providers', label: 'Providers' },
  { id: 'files', label: 'Files' },
  { id: 'policies', label: 'Policies' },
  { id: 'health', label: 'Health/Export' },
];

/** Skills — the rendered tab bar, in order. */
export const SKILLS_TABS: ScreenTabDef<SkillsTabId>[] = [
  { id: 'library', label: 'Skills Library' },
  { id: 'start', label: 'Start Here' },
  { id: 'project', label: 'Project Skills' },
  { id: 'bundles', label: 'Bundles' },
  { id: 'learn', label: 'Learn a Skill' },
  { id: 'learning', label: 'Learning Queue' },
  { id: 'journey', label: 'Journey' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'evaluation', label: 'Evaluation Center' },
  { id: 'activity', label: 'Execution Activity' },
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
