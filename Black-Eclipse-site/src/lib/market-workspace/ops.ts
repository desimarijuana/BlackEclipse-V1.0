// ── Market Workspace — pure layout operations ────────────────────────────────
// Every function MUTATES the layout it is given and is meant to run inside an
// Immer `produce`. Nothing touches the DOM or storage, so it is all unit-testable.

import {
  clampRect,
  gridPreset,
  GRID_COLUMNS,
  MAX_ROWS,
  MIN_PANEL_COLS,
  MIN_PANEL_ROWS,
  newPanelId,
  presetRect,
  rectsOverlap,
  type MarketPanel,
  type MarketPanelType,
  type MarketWorkspaceLayout,
  type PanelRect,
} from './types';
import { defaultChartState } from '@/lib/chart/types';
import type { Draft } from 'immer';

/** Deep-ish clone so snapshots/templates never share panel objects. */
export function cloneLayout(l: MarketWorkspaceLayout): MarketWorkspaceLayout {
  return {
    version: 1,
    layoutId: l.layoutId,
    rows: l.rows,
    panels: l.panels.map(p => ({
      ...p,
      rect: { ...p.rect },
      chart: p.chart
        ? {
            ...p.chart,
            indicators: [...p.chart.indicators],
            drawings: [...p.chart.drawings],
            compare: [...(p.chart.compare ?? [])],
          }
        : undefined,
      link: p.link ? { ...p.link } : undefined,
      config: p.config ? { ...p.config } : undefined,
    })),
  };
}

export function emptyLayout(layoutId = '2x2'): MarketWorkspaceLayout {
  const { columns, rows } = gridPreset(layoutId);
  return { version: 1, layoutId, rows, panels: [makePanel('chart', 0, columns)] };
}

/** Build a panel with a preset cell placement. */
export function makePanel(type: MarketPanelType, index: number, columns: number): MarketPanel {
  const rect = presetRect(index, columns);
  const panel: MarketPanel = { id: newPanelId(type), type, rect };
  if (type === 'chart') panel.chart = defaultChartState({ symbol: 'AAPL', market: 'US' });
  return panel;
}

/** Find the lowest row a rect can occupy without overlapping (compaction). */
export function firstFreeRow(panels: MarketPanel[], rect: PanelRect, ignoreId?: string): number {
  let row = 0;
  const others = panels.filter(p => p.id !== ignoreId);
  for (let guard = 0; guard < MAX_ROWS * 2; guard++) {
    const candidate = { ...rect, row };
    if (!others.some(p => rectsOverlap(candidate, p.rect))) return row;
    row += 1;
  }
  return row;
}

/**
 * Default size for a NEW panel. Presets tile into their logical columns
 * (3-col preset → 4 units wide, one row tall). A custom workspace has no
 * logical columns, so new panels get a generous half-width, two-row-tall chart
 * — big enough to read immediately, never a 1-unit sliver.
 */
function defaultPanelSize(layoutId: string): { colSpan: number; rowSpan: number } {
  if (layoutId === 'custom') {
    return { colSpan: Math.floor(GRID_COLUMNS / 2), rowSpan: 2 };
  }
  const { columns } = gridPreset(layoutId);
  return { colSpan: Math.max(MIN_PANEL_COLS, Math.floor(GRID_COLUMNS / Math.max(1, columns))), rowSpan: 1 };
}

/**
 * First-fit slot scan: rows top→bottom, columns left→right, returning the first
 * position where a `colSpan × rowSpan` rect clears every existing panel. Grows
 * the returned row past the current layout when needed so a new panel never
 * stacks awkwardly at the far left below everything.
 */
export function findFreeSlot(panels: MarketPanel[], colSpan: number, rowSpan: number): { col: number; row: number } {
  const span = Math.min(GRID_COLUMNS, Math.max(MIN_PANEL_COLS, colSpan));
  const maxRow = panels.reduce((a, p) => Math.max(a, p.rect.row + p.rect.rowSpan), 0);
  for (let row = 0; row <= maxRow; row++) {
    for (let col = 0; col + span <= GRID_COLUMNS; col++) {
      const candidate: PanelRect = { col, row, colSpan: span, rowSpan: Math.max(MIN_PANEL_ROWS, rowSpan) };
      if (!panels.some(p => rectsOverlap(candidate, p.rect))) return { col, row };
    }
  }
  // Nothing fit inside the existing rows — drop it on a fresh row at the left.
  return { col: 0, row: maxRow };
}

/** Clamp every rect, then re-flow overlaps downward. Order is preserved. */
export function normalizePanels(d: Draft<MarketWorkspaceLayout>): void {
  const placed: MarketPanel[] = [];
  for (const panel of d.panels) {
    const rect = clampRect(panel.rect, d.rows);
    rect.row = firstFreeRow(placed, rect);
    panel.rect = rect;
    placed.push(panel);
  }
  const maxRow = placed.reduce((a, p) => Math.max(a, p.rect.row + p.rect.rowSpan), 0);
  if (maxRow > d.rows) d.rows = Math.min(MAX_ROWS, maxRow);
}

/**
 * Add a panel at a sensible size, first-fit packed into the first free slot so
 * it shows up big and immediately visible — never a 1-unit sliver, never
 * buried at the far-left of a new row when space exists above.
 */
export function addPanel(d: Draft<MarketWorkspaceLayout>, type: MarketPanelType, rect?: PanelRect): MarketPanel {
  const { columns } = gridPreset(d.layoutId);
  const index = d.panels.length;
  const panel = makePanel(type, index, columns);
  if (rect) {
    panel.rect = clampRect(rect, Math.max(d.rows + rect.row + rect.rowSpan, d.rows));
    panel.rect.row = firstFreeRow(d.panels, panel.rect);
  } else {
    const { colSpan, rowSpan } = defaultPanelSize(d.layoutId);
    const slot = findFreeSlot(d.panels, colSpan, rowSpan);
    panel.rect = { col: slot.col, row: slot.row, colSpan, rowSpan };
  }
  d.panels.push(panel);
  const needed = panel.rect.row + panel.rect.rowSpan;
  if (needed > d.rows) d.rows = Math.min(MAX_ROWS, needed);
  return panel;
}

export function removePanel(d: Draft<MarketWorkspaceLayout>, id: string): void {
  d.panels = d.panels.filter(p => p.id !== id);
}

/** Duplicate a panel (new id), placed below the original via compaction. */
export function duplicatePanel(d: Draft<MarketWorkspaceLayout>, id: string): void {
  const idx = d.panels.findIndex(p => p.id === id);
  if (idx === -1) return;
  const src = d.panels[idx];
  const copy: MarketPanel = {
    ...src,
    id: newPanelId(src.type),
    rect: { ...src.rect, row: src.rect.row + src.rect.rowSpan },
    chart: src.chart
      ? { ...src.chart, drawings: src.chart.drawings.map(dr => ({ ...dr, id: `${dr.id}-copy` })) }
      : undefined,
    config: src.config ? { ...src.config } : undefined,
  };
  copy.rect.row = firstFreeRow(d.panels, copy.rect);
  d.panels.splice(idx + 1, 0, copy);
}

export function setPanelRect(d: Draft<MarketWorkspaceLayout>, id: string, rect: PanelRect): void {
  const panel = d.panels.find(p => p.id === id);
  if (!panel) return;
  panel.rect = clampRect(rect, d.rows);
}

/** Update a chart panel's serializable chart state. */
export function setPanelChart(d: Draft<MarketWorkspaceLayout>, id: string, chart: MarketPanel['chart']): void {
  const panel = d.panels.find(p => p.id === id);
  if (panel) panel.chart = chart;
}

/** Update a panel's symbol/market context (drives chart + panels). */
export function setPanelSymbol(d: Draft<MarketWorkspaceLayout>, id: string, symbol: string, market?: string): void {
  const panel = d.panels.find(p => p.id === id);
  if (!panel) return;
  panel.symbol = symbol.toUpperCase();
  if (market) panel.market = market;
  if (panel.chart) {
    panel.chart = { ...panel.chart, symbol: symbol.toUpperCase(), ...(market ? { market } : {}) };
  }
}

export function setPanelLink(d: Draft<MarketWorkspaceLayout>, id: string, link: MarketPanel['link']): void {
  const panel = d.panels.find(p => p.id === id);
  if (panel) panel.link = link;
}

export function setPanelConfig(d: Draft<MarketWorkspaceLayout>, id: string, patch: Record<string, unknown>): void {
  const panel = d.panels.find(p => p.id === id);
  if (!panel) return;
  panel.config = { ...(panel.config ?? {}), ...patch };
}

export function togglePanelAi(d: Draft<MarketWorkspaceLayout>, id: string): void {
  const panel = d.panels.find(p => p.id === id);
  if (panel) panel.aiOpen = !panel.aiOpen;
}

/**
 * Re-tile every panel into a preset's NxM grid (row-major). Panels keep their
 * content/state; only placement changes. Extra panels spill into more rows.
 */
export function applyGridPreset(d: Draft<MarketWorkspaceLayout>, layoutId: string): void {
  const { columns, rows } = gridPreset(layoutId);
  const perRow = Math.max(1, columns);
  const colSpan = Math.max(MIN_PANEL_COLS, Math.floor(GRID_COLUMNS / perRow));
  d.layoutId = layoutId;
  d.rows = rows;
  d.panels.forEach((panel, i) => {
    panel.rect = { col: (i % perRow) * colSpan, row: Math.floor(i / perRow), colSpan, rowSpan: 1 };
  });
  normalizePanels(d);
}

/** Auto-arrange panels into a compact flow with sensible spans. */
export function autoArrange(d: Draft<MarketWorkspaceLayout>): void {
  const n = d.panels.length;
  const perRow = n <= 1 ? 1 : n <= 4 ? 2 : n <= 9 ? 3 : 4;
  const colSpan = Math.max(MIN_PANEL_COLS, Math.floor(GRID_COLUMNS / perRow));
  d.panels.forEach((panel, i) => {
    panel.rect = { col: (i % perRow) * colSpan, row: Math.floor(i / perRow), colSpan, rowSpan: 1 };
  });
  d.rows = Math.max(1, Math.ceil(n / perRow));
  d.layoutId = perRow === 1 ? '1x1' : perRow === 2 ? '2x2' : perRow === 3 ? '3x2' : '4x2';
}

// ── Validation / migration ───────────────────────────────────────────────────

function asRect(raw: unknown): PanelRect | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const col = Number(r.col), row = Number(r.row), colSpan = Number(r.colSpan), rowSpan = Number(r.rowSpan);
  if (![col, row, colSpan, rowSpan].every(Number.isFinite)) return null;
  return { col, row, colSpan, rowSpan };
}

function asPanel(raw: unknown): MarketPanel | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || !r.id || typeof r.type !== 'string') return null;
  const rect = asRect(r.rect);
  if (!rect) return null;
  const panel: MarketPanel = { id: r.id, type: r.type as MarketPanelType, rect };
  if (r.chart && typeof r.chart === 'object') panel.chart = r.chart as MarketPanel['chart'];
  if (typeof r.symbol === 'string') panel.symbol = r.symbol;
  if (typeof r.market === 'string') panel.market = r.market;
  if (r.link && typeof r.link === 'object') panel.link = r.link as MarketPanel['link'];
  if (r.aiOpen === true) panel.aiOpen = true;
  if (r.config && typeof r.config === 'object' && !Array.isArray(r.config)) panel.config = r.config as Record<string, unknown>;
  return panel;
}

/**
 * Repair an untrusted stored layout. Returns a clean layout or null when the
 * payload is unusable — callers fall back to defaults WITHOUT overwriting it.
 */
export function normalizeLayout(raw: unknown): MarketWorkspaceLayout | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (!Array.isArray(r.panels)) return null;
  const seen = new Set<string>();
  const panels: MarketPanel[] = [];
  for (const rawPanel of r.panels) {
    const p = asPanel(rawPanel);
    if (!p || seen.has(p.id)) continue;
    seen.add(p.id);
    panels.push(p);
  }
  if (panels.length === 0) return null;
  const layoutId = typeof r.layoutId === 'string' ? r.layoutId : 'custom';
  const rows = typeof r.rows === 'number' && Number.isFinite(r.rows)
    ? Math.max(1, Math.min(MAX_ROWS, Math.round(r.rows)))
    : 4;
  const layout: MarketWorkspaceLayout = { version: 1, layoutId, rows, panels };
  normalizePanels(layout as Draft<MarketWorkspaceLayout>);
  return layout;
}
