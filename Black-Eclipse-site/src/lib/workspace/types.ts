// ── Workspace kernel types ──────────────────────────────────────────────────
// A generic, free-form layout model: sections (rows) → columns (1–4, relative
// weights) → widget cards stacked vertically. Widgets are referenced by id
// only — the kernel never knows what a widget is.

export interface WidgetPlacement {
  /** Unique instance id (a widget can appear multiple times). */
  id: string;
  /** Registry id of the widget to render. */
  widgetId: string;
  /** Fixed pixel height; null = natural/auto height. */
  height: number | null;
  /** Per-instance configuration (widget-specific, opaque to the kernel). */
  config?: Record<string, unknown>;
  /** True when the widget is hidden (kept in the layout, not rendered). */
  hidden?: boolean;
}

export interface WorkspaceColumn {
  id: string;
  /** Relative width weight, 1..6. */
  weight: number;
  widgets: WidgetPlacement[];
}

/**
 * Which canvas column a section belongs to. `left` and `right` are the narrow
 * side columns beside the primary/centre `main` canvas (e.g. the Command Center
 * Watchlist and Market panels). All render under the SAME workspace +
 * DndContext, so cards drag freely between them. Undefined = `main`.
 *
 * Legacy note: stored layouts from the two-zone era use `'rail'` for the right
 * column. `normalizeLayout` maps `'rail'` → `'right'` on read, so no storage
 * bump is required.
 */
export type WorkspaceZone = 'left' | 'main' | 'right';

export interface WorkspaceSection {
  id: string;
  columns: WorkspaceColumn[];
  /** Defaults to 'main' when omitted (legacy layouts). */
  zone?: WorkspaceZone;
}

export interface WorkspaceLayout {
  version: 1;
  sections: WorkspaceSection[];
  /**
   * Zones the user has removed from view. Their sections are KEPT in `sections`
   * (so re-showing restores the exact arrangement) but not rendered. Persisted
   * so a panel stays removed across reloads.
   */
  hiddenZones?: WorkspaceZone[];
}

/** Where a dragged card should land. columnId=null means "create a new column". */
export interface DropTarget {
  sectionId: string;
  columnId: string | null;
  index: number;
  /** When columnId is null: position to insert the fresh column (default: end). */
  columnIndex?: number;
}

export const MIN_COLUMN_WEIGHT = 0.3;
export const MAX_COLUMN_WEIGHT = 12;
export const MIN_WIDGET_HEIGHT = 140;

let counter = 0;
export function newId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
