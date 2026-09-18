// ── Workspace kernel types ──────────────────────────────────────────────────
// A generic, track-based layout model: a board of vertical tracks (columns),
// each a stack of widget cards. Sections exist only as zones/anchors, but the
// DEFAULT arrangement is one section per zone whose columns ARE the tracks, and
// widgets are packed into the shortest track (see pack.ts) so a short card
// never leaves a hole beside a tall one. Widgets are referenced by id only —
// the kernel never knows what a widget is.

export interface WidgetPlacement {
  /** Unique instance id (a widget can appear multiple times). */
  id: string;
  /** Registry id of the widget to render. */
  widgetId: string;
  /** Pinned pixel height; null = natural/content height (the default). */
  height: number | null;
  /**
   * Preferred definite height (px) for boxes whose content fills the card and
   * cannot size itself — charts, maps, live video, scrollable lists. The card
   * gets this as a `min-height` and its body stretches to it. Distinct from
   * `minHeight`, which is a floor under content that GROWS (tiles).
   */
  defaultHeight?: number;
  /** Content-derived minimum height floor for cards that grow (tiles). */
  minHeight?: number;
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
  /**
   * 1 = legacy row-band grammar (retired). 2 = track board (current): widgets
   * are packed into the shortest track and size to content by default.
   */
  version: 1 | 2;
  sections: WorkspaceSection[];
  /**
   * User-resized side-zone widths in px. Presentation-only (does not affect the
   * tree) but persisted with the layout so a widened Watchlist survives reload.
   */
  zoneWidths?: { left?: number; right?: number };
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
/** Floor for a pinned/resized card height (content default is auto). */
export const MIN_WIDGET_HEIGHT = 140;
/** Resizable side-zone width bounds (px). */
export const MIN_ZONE_WIDTH = 180;
export const MAX_ZONE_WIDTH = 520;
/** Current layout schema version (track board). */
export const WORKSPACE_VERSION = 2 as const;

let counter = 0;
export function newId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
