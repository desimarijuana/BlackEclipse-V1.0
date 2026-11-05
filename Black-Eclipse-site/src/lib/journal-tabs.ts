// ─── Journal tabs — the ONE list ─────────────────────────────────────────────
// The rendered Journal tab bar, in order. Imported by BOTH the screen (for
// the bar itself) and the search registry (to generate palette sub-page
// entries), so a Journal view can never exist in the bar but be unreachable
// from ⌘K. Icons live in the screen (keyed by id); this module stays pure.

export type JournalTabId =
  | 'overview' | 'calendar' | 'trades' | 'analytics' | 'decisions'
  | 'psychology' | 'playbook' | 'reviews' | 'insights' | 'notebook';

export interface JournalTabDef {
  id: JournalTabId;
  /** User-visible label exactly as the tab bar renders it. */
  label: string;
}

export const JOURNAL_TABS: JournalTabDef[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'trades', label: 'Trades' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'decisions', label: 'Decisions' },
  { id: 'psychology', label: 'Psychology' },
  { id: 'playbook', label: 'Playbook' },
  { id: 'reviews', label: 'Reviews' },
  { id: 'insights', label: 'Insights' },
  { id: 'notebook', label: 'Notebook' },
];
