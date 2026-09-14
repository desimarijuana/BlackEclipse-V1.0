// ── Market Workspace — grid kernel types ─────────────────────────────────────
// A dense, free-form panel grid for the multi-chart trading terminal. Panels are
// placed on a 12-column × N-row grid and may SPAN multiple rows/columns, so the
// user can build asymmetric layouts (one big chart beside two stacked charts)
// that a simple NxM grid cannot express.
//
// This is a sibling of the widget kernel (@/lib/workspace): it reuses the same
// design language and persistence discipline but adds grid coordinates, panel
// drag/resize, and linked-chart state — the things a charting terminal needs.
//
// Panel CONTENT is referenced by a `panelType` id only; the kernel never knows
// what a chart or an AI panel is.

import type { ChartState } from '@/lib/chart/types';

/** Kinds of panel the workspace can host. */
export type MarketPanelType =
  | 'chart'
  | 'watchlist'
  | 'market-overview'
  | 'news'
  | 'fundamentals'
  | 'economic-calendar'
  | 'ai-analysis'
  | 'portfolio'
  | 'heatmap'
  | 'alerts'
  | 'screener';

export const MARKET_PANEL_TYPES: MarketPanelType[] = [
  'chart', 'watchlist', 'market-overview', 'news', 'fundamentals',
  'economic-calendar', 'ai-analysis', 'portfolio', 'heatmap', 'alerts', 'screener',
];

/** Linked-chart behaviours. Any subset may be enabled on a panel. */
export interface ChartLink {
  /** Mirror symbol changes across linked charts. */
  symbol: boolean;
  /** Mirror timeframe changes across linked charts. */
  timeframe: boolean;
  /** Share the crosshair timestamp across linked charts. */
  crosshair: boolean;
  /** Sync the visible data range (zoom) across linked charts. */
  range: boolean;
}

export const DEFAULT_LINK: ChartLink = { symbol: false, timeframe: false, crosshair: false, range: false };

/** A panel's placement on the workspace grid (0-indexed cells). */
export interface PanelRect {
  col: number;
  row: number;
  colSpan: number;
  rowSpan: number;
}

/** Per-panel persisted state. Chart panels carry a full ChartState. */
export interface MarketPanel {
  /** Unique instance id. */
  id: string;
  type: MarketPanelType;
  /** Grid placement. */
  rect: PanelRect;
  /** Chart state for `chart` panels (symbol/timeframe/type/indicators/drawings). */
  chart?: ChartState;
  /** Symbol context for non-chart panels (watchlist/news/fundamentals/ai). */
  symbol?: string;
  market?: string;
  /** Linked-chart toggles (charts only). */
  link?: ChartLink;
  /** AI analysis drawer open state (charts). */
  aiOpen?: boolean;
  /** Per-panel opaque config. */
  config?: Record<string, unknown>;
}

/** A named workspace layout: an ordered set of panels + grid dimensions. */
export interface MarketWorkspaceLayout {
  version: 1;
  /** Grid template name or 'custom'. */
  layoutId: string;
  /** Grid row tracks (columns are always 12). */
  rows: number;
  panels: MarketPanel[];
}

/** A named grid layout preset (logical N columns × M rows). */
export interface GridPreset {
  id: string;
  label: string;
  /** Logical columns in the preset (panels tile at 12/columns each). */
  columns: number;
  /** Logical rows. */
  rows: number;
}

export const GRID_COLUMNS = 12;
export const MAX_ROWS = 24;
export const MIN_PANEL_COLS = 2;
export const MIN_PANEL_ROWS = 1;

export const GRID_PRESETS: GridPreset[] = [
  { id: '1x1', label: '1 × 1', columns: 1, rows: 1 },
  { id: '2x1', label: '2 × 1', columns: 2, rows: 1 },
  { id: '2x2', label: '2 × 2', columns: 2, rows: 2 },
  { id: '3x1', label: '3 × 1', columns: 3, rows: 1 },
  { id: '3x2', label: '3 × 2', columns: 3, rows: 2 },
  { id: '3x3', label: '3 × 3', columns: 3, rows: 3 },
  { id: '4x2', label: '4 × 2', columns: 4, rows: 2 },
  { id: '4x3', label: '4 × 3', columns: 4, rows: 3 },
];

export function gridPreset(id: string): { columns: number; rows: number } {
  if (id === 'custom') return { columns: GRID_COLUMNS, rows: 8 };
  return GRID_PRESETS.find(p => p.id === id) ?? { columns: 3, rows: 2 };
}

let counter = 0;
export function newPanelId(prefix = 'panel'): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * The default rect for panel `index` in a preset layout (row-major tiling).
 * Column spans always land on the 12-unit grid so a 3-col preset gives each
 * panel 4 units.
 */
export function presetRect(index: number, columns: number): PanelRect {
  const perRow = Math.max(1, columns);
  const colSpan = Math.max(1, Math.floor(GRID_COLUMNS / perRow));
  const col = (index % perRow) * colSpan;
  const row = Math.floor(index / perRow);
  return { col, row, colSpan, rowSpan: 1 };
}

/** True when two rects overlap on the grid. */
export function rectsOverlap(a: PanelRect, b: PanelRect): boolean {
  return (
    a.col < b.col + b.colSpan &&
    a.col + a.colSpan > b.col &&
    a.row < b.row + b.rowSpan &&
    a.row + a.rowSpan > b.row
  );
}

/** Clamp a rect so it stays inside the 12-column grid and the row bounds. */
export function clampRect(rect: PanelRect, rows = MAX_ROWS): PanelRect {
  const colSpan = Math.max(MIN_PANEL_COLS, Math.min(rect.colSpan, GRID_COLUMNS));
  const rowSpan = Math.max(MIN_PANEL_ROWS, Math.min(rect.rowSpan, MAX_ROWS));
  const col = Math.max(0, Math.min(rect.col, GRID_COLUMNS - colSpan));
  const row = Math.max(0, Math.min(rect.row, Math.max(0, rows - rowSpan)));
  return { col, row, colSpan, rowSpan };
}
