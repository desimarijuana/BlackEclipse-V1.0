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
}

export interface WorkspaceColumn {
  id: string;
  /** Relative width weight, 1..6. */
  weight: number;
  widgets: WidgetPlacement[];
}

export interface WorkspaceSection {
  id: string;
  columns: WorkspaceColumn[];
}

export interface WorkspaceLayout {
  version: 1;
  sections: WorkspaceSection[];
}

/** Where a dragged card should land. columnId=null means "create a new column". */
export interface DropTarget {
  sectionId: string;
  columnId: string | null;
  index: number;
  /** When columnId is null: position to insert the fresh column (default: end). */
  columnIndex?: number;
}

export const MIN_COLUMN_WEIGHT = 1;
export const MAX_COLUMN_WEIGHT = 6;
export const MIN_WIDGET_HEIGHT = 140;

let counter = 0;
export function newId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
