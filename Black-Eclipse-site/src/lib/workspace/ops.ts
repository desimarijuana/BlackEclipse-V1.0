// ── Pure layout operations (Immer drafts) ────────────────────────────────────
// Every function MUTATES the layout it is given and is meant to be invoked
// inside an Immer `produce` — copy-on-write makes that safe and keeps the
// result immutable for React. Nothing here touches the DOM or storage, so it
// is all unit-testable (tests wrap calls in `produce` and return the draft).

import {
  MAX_COLUMN_WEIGHT,
  MAX_ZONE_WIDTH,
  MIN_COLUMN_WEIGHT,
  MIN_WIDGET_HEIGHT,
  MIN_ZONE_WIDTH,
  WORKSPACE_VERSION,
  newId,
  type DropTarget,
  type WorkspaceColumn,
  type WorkspaceLayout,
  type WorkspaceSection,
  type WorkspaceZone,
  type WidgetPlacement,
} from './types';
import type { Draft } from 'immer';

export function cloneLayout(l: WorkspaceLayout): WorkspaceLayout {
  return {
    version: WORKSPACE_VERSION,
    sections: l.sections.map(s => ({
      id: s.id,
      zone: s.zone,
      columns: s.columns.map(c => ({
        id: c.id,
        weight: c.weight,
        widgets: c.widgets.map(w => ({
          ...w,
          config: w.config ? { ...w.config } : undefined,
        })),
      })),
    })),
    hiddenZones: l.hiddenZones ? [...l.hiddenZones] : undefined,
    zoneWidths: l.zoneWidths ? { ...l.zoneWidths } : undefined,
  };
}

export function emptyLayout(): WorkspaceLayout {
  return {
    version: WORKSPACE_VERSION,
    sections: [{
      id: newId('sec'),
      zone: 'main',
      columns: [{ id: newId('col'), weight: 3, widgets: [] }],
    }],
  };
}

export function widgetCount(l: WorkspaceLayout): number {
  return l.sections.reduce((a, s) => a + s.columns.reduce((b, c) => b + c.widgets.length, 0), 0);
}

export function allWidgetIds(l: WorkspaceLayout): string[] {
  return l.sections.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId)));
}

export function locate(l: WorkspaceLayout, widgetId: string):
  { section: WorkspaceSection; column: WorkspaceColumn; widget: WidgetPlacement; index: number } | null {
  for (const section of l.sections) {
    for (const column of section.columns) {
      const index = column.widgets.findIndex(w => w.id === widgetId);
      if (index !== -1) return { section, column, widget: column.widgets[index], index };
    }
  }
  return null;
}

/**
 * Prune sections that have no widgets at all (keeping at least one section).
 * Empty columns are PRESERVED — they are legitimate drop targets for the
 * drag-and-drop editor, and setColumnCount owns column counts.
 */
export function pruneLayout(d: Draft<WorkspaceLayout>): void {
  const nonEmpty = d.sections.filter(s => s.columns.some(c => c.widgets.length > 0));
  if (nonEmpty.length === 0) {
    // Keep the first section alive with a single column so the canvas is
    // still a drop target; drop truly empty extra sections.
    if (d.sections.length > 0) {
      d.sections = [{
        id: d.sections[0].id,
        zone: d.sections[0].zone,
        columns: d.sections[0].columns.length > 0 ? d.sections[0].columns : [{ id: newId('col'), weight: 3, widgets: [] }],
      }];
    }
    return;
  }
  d.sections = nonEmpty.map(s => ({
    id: s.id,
    zone: s.zone,
    columns: s.columns.length > 0 ? s.columns : [{ id: newId('col'), weight: 3, widgets: [] }],
  }));
}

/** Take a widget out of the tree, returning it (mutates the draft). */
function takeWidget(d: Draft<WorkspaceLayout>, widgetId: string): WidgetPlacement | null {
  for (const s of d.sections) {
    for (const c of s.columns) {
      const i = c.widgets.findIndex(w => w.id === widgetId);
      if (i !== -1) return c.widgets.splice(i, 1)[0];
    }
  }
  return null;
}

function draftColumn(d: Draft<WorkspaceLayout>, sectionId: string, columnId: string | null): Draft<WorkspaceColumn> | null {
  const section = d.sections.find(s => s.id === sectionId);
  if (!section) return null;
  if (columnId === null) {
    const column: WorkspaceColumn = { id: newId('col'), weight: 3, widgets: [] };
    section.columns.push(column);
    return section.columns[section.columns.length - 1];
  }
  return section.columns.find(c => c.id === columnId) ?? null;
}

/**
 * Move a widget card to a drop target. columnId=null creates a fresh column
 * (at target.columnIndex when given, else at the end of the section). The
 * index refers to positions AFTER removal of the card from its origin
 * (insertion index among the remaining siblings).
 */
export function moveWidget(d: Draft<WorkspaceLayout>, widgetId: string, target: DropTarget): void {
  const moved = takeWidget(d, widgetId);
  if (!moved) return;
  let column: Draft<WorkspaceColumn> | null = null;
  if (target.columnId === null) {
    const section = d.sections.find(s => s.id === target.sectionId);
    if (section) {
      const fresh: WorkspaceColumn = { id: newId('col'), weight: 3, widgets: [] };
      const at = Math.max(0, Math.min(target.columnIndex ?? section.columns.length, section.columns.length));
      section.columns.splice(at, 0, fresh);
      column = section.columns[at];
    }
  } else {
    column = draftColumn(d, target.sectionId, target.columnId);
  }
  if (!column) { pruneLayout(d); return; }
  const index = Math.max(0, Math.min(target.index, column.widgets.length));
  column.widgets.splice(index, 0, moved);
  pruneLayout(d);
}

/** Move a card into a brand-new section (single column) appended at the end. */
export function moveWidgetToNewSection(d: Draft<WorkspaceLayout>, widgetId: string): void {
  const moved = takeWidget(d, widgetId);
  if (!moved) return;
  d.sections.push({ id: newId('sec'), zone: 'main', columns: [{ id: newId('col'), weight: 3, widgets: [moved] }] });
  pruneLayout(d);
}

/**
 * Move a card into a brand-new section inserted relative to an existing
 * section: before it (above) or after it (below). This is what powers the
 * inter-section "+" strips in the editor. The new section inherits the anchor
 * section's zone so a strip in the rail creates a rail section.
 */
export function moveWidgetToNewSectionAt(
  d: Draft<WorkspaceLayout>,
  widgetId: string,
  anchorSectionId: string,
  position: 'above' | 'below',
): void {
  // Resolve the anchor position BEFORE taking the widget — taking can empty
  // (and prune away) the anchor section itself, e.g. dragging the only card
  // of a section onto that section's own above/below strip.
  const anchorIdx = d.sections.findIndex(s => s.id === anchorSectionId);
  const anchorZone = anchorIdx === -1 ? 'main' : (d.sections[anchorIdx].zone ?? 'main');
  const moved = takeWidget(d, widgetId);
  if (!moved) return;
  const insertAt = anchorIdx === -1
    ? d.sections.length
    : position === 'above' ? anchorIdx : anchorIdx + 1;
  d.sections.splice(insertAt, 0, { id: newId('sec'), zone: anchorZone, columns: [{ id: newId('col'), weight: 3, widgets: [moved] }] });
  pruneLayout(d);
}

/**
 * Create an empty section above/below an anchor section (click affordance on
 * the inter-section strips). Empty sections are preserved — the user just
 * asked for one; pruneLayout only runs through moves. Inherits the anchor's zone.
 */
export function createSectionAt(
  d: Draft<WorkspaceLayout>,
  anchorSectionId: string,
  position: 'above' | 'below',
): void {
  const anchorIdx = d.sections.findIndex(s => s.id === anchorSectionId);
  const anchorZone = anchorIdx === -1 ? 'main' : (d.sections[anchorIdx].zone ?? 'main');
  const insertAt = anchorIdx === -1
    ? d.sections.length
    : position === 'above' ? anchorIdx : anchorIdx + 1;
  d.sections.splice(insertAt, 0, { id: newId('sec'), zone: anchorZone, columns: [{ id: newId('col'), weight: 3, widgets: [] }] });
}

/**
 * Remove an entire section (and its columns/widgets). Always leaves at least
 * one section in the layout so the canvas remains a valid drop target.
 */
export function removeSection(d: Draft<WorkspaceLayout>, sectionId: string): void {
  const idx = d.sections.findIndex(s => s.id === sectionId);
  if (idx === -1) return;
  d.sections.splice(idx, 1);
  if (d.sections.length === 0) {
    d.sections.push({ id: newId('sec'), zone: 'main', columns: [{ id: newId('col'), weight: 3, widgets: [] }] });
  }
}

/** Create an empty section in a specific zone (used to re-seed a side panel). */
export function createSectionInZone(d: Draft<WorkspaceLayout>, zone: WorkspaceZone): void {
  d.sections.push({ id: newId('sec'), zone, columns: [{ id: newId('col'), weight: 3, widgets: [] }] });
}

/**
 * Hide or show a whole zone (left/right panel). Hiding KEEPS the zone's
 * sections in the tree so re-showing restores the exact arrangement — it is
 * never a delete. Mutates `hiddenZones` only.
 */
export function setZoneHidden(d: Draft<WorkspaceLayout>, zone: WorkspaceZone, hidden: boolean): void {
  const current = d.hiddenZones ?? [];
  const without = current.filter(z => z !== zone);
  d.hiddenZones = hidden ? [...without, zone] : (without.length > 0 ? without : undefined);
}

/**
 * Set a side zone's width (px). Presentation-only — clamped to the bounds and
 * persisted so a widened panel survives reload. `main` is not resizable.
 */
export function setZoneWidth(d: Draft<WorkspaceLayout>, zone: WorkspaceZone, width: number | null): void {
  if (zone === 'main') return;
  if (width === null || !Number.isFinite(width)) {
    const next = d.zoneWidths ? { ...d.zoneWidths, [zone]: undefined } : undefined;
    d.zoneWidths = next && (next.left != null || next.right != null) ? next : undefined;
    return;
  }
  const clamped = Math.max(MIN_ZONE_WIDTH, Math.min(MAX_ZONE_WIDTH, Math.round(width)));
  d.zoneWidths = { ...(d.zoneWidths ?? {}), [zone]: clamped };
}

/**
 * Add a NEW widget into a brand-new section inserted above/below an anchor.
 * Used when dragging a widget in from the library straight onto an
 * inter-section strip. The new section always has a single column holding it.
 */
export function addWidgetToNewSectionAt(
  d: Draft<WorkspaceLayout>,
  widgetId: string,
  anchorSectionId: string,
  position: 'above' | 'below',
  sizing?: PlacementSizing,
): void {
  const anchorIdx = d.sections.findIndex(s => s.id === anchorSectionId);
  const anchorZone = anchorIdx === -1 ? 'main' : (d.sections[anchorIdx].zone ?? 'main');
  const insertAt = anchorIdx === -1
    ? d.sections.length
    : position === 'above' ? anchorIdx : anchorIdx + 1;
  const widget: WidgetPlacement = { id: newId('wid'), widgetId, height: null, ...(sizing ?? {}) };
  d.sections.splice(insertAt, 0, { id: newId('sec'), zone: anchorZone, columns: [{ id: newId('col'), weight: 3, widgets: [widget] }] });
}

/** Intrinsic sizing hint applied to a freshly added widget (see widget-def). */
export interface PlacementSizing {
  defaultHeight?: number;
  minHeight?: number;
}

export function addWidget(d: Draft<WorkspaceLayout>, widgetId: string, target?: DropTarget, sizing?: PlacementSizing): void {
  const widget: WidgetPlacement = { id: newId('wid'), widgetId, height: null, ...(sizing ?? {}) };
  if (d.sections.length === 0) d.sections.push({ id: newId('sec'), columns: [] });

  let section = target ? d.sections.find(s => s.id === target.sectionId) : undefined;
  if (!section) section = d.sections[d.sections.length - 1];

  let column: Draft<WorkspaceColumn> | undefined;
  if (target && target.columnId === null) {
    // Explicit "new column" target, inserted at columnIndex (default: end).
    const at = Math.max(0, Math.min(target.columnIndex ?? section.columns.length, section.columns.length));
    column = { id: newId('col'), weight: 3, widgets: [] };
    section.columns.splice(at, 0, column);
  } else if (target) {
    column = section.columns.find(c => c.id === target.columnId);
  }
  if (!column) column = section.columns[section.columns.length - 1];
  if (!column) {
    column = { id: newId('col'), weight: 3, widgets: [] };
    section.columns.push(column);
    column = section.columns[section.columns.length - 1];
  }
  const index = target && column.id === target.columnId
    ? Math.max(0, Math.min(target.index, column.widgets.length))
    : column.widgets.length;
  column.widgets.splice(index, 0, widget);
}

export function removeWidget(d: Draft<WorkspaceLayout>, widgetId: string): void {
  for (const s of d.sections) {
    for (const c of s.columns) {
      if (c.widgets.some(w => w.id === widgetId)) {
        c.widgets = c.widgets.filter(w => w.id !== widgetId);
        pruneLayout(d);
        return;
      }
    }
  }
}

/** Set a section's column count (1..4), relocating displaced cards into the last column. */
export function setColumnCount(d: Draft<WorkspaceLayout>, sectionId: string, count: number): void {
  const clamped = Math.max(1, Math.min(4, Math.round(count)));
  const section = d.sections.find(s => s.id === sectionId);
  if (!section) return;

  if (section.columns.length > clamped) {
    const overflow = section.columns.splice(clamped);
    const last = section.columns[section.columns.length - 1];
    for (const c of overflow) last.widgets.push(...c.widgets);
  }
  while (section.columns.length < clamped) {
    section.columns.push({ id: newId('col'), weight: 3, widgets: [] });
  }
  // NOTE: deliberately NO pruneLayout here. An empty section is a legitimate
  // user-created drop target (createSectionAt preserves it), so adding columns
  // to it must not let pruneLayout delete it out from under the user.
}

function clampWeight(weight: number): number {
  return Math.max(MIN_COLUMN_WEIGHT, Math.min(MAX_COLUMN_WEIGHT, Math.round(weight * 10) / 10));
}

export function setColumnWeight(d: Draft<WorkspaceLayout>, columnId: string, weight: number): void {
  // Float weights (0.1 steps): integer weights quantized so repeated resizes
  // often produced the same value and the handle appeared stuck.
  const clamped = clampWeight(weight);
  for (const s of d.sections) {
    const c = s.columns.find(col => col.id === columnId);
    if (c) { c.weight = clamped; return; }
  }
}

/**
 * Set several column weights atomically (used by the boundary resize handle,
 * which grows one column while shrinking its neighbour so the section total —
 * and therefore every other column — stays put).
 */
export function setColumnWeights(
  d: Draft<WorkspaceLayout>,
  sectionId: string,
  updates: ReadonlyArray<{ columnId: string; weight: number }>,
): void {
  const section = d.sections.find(s => s.id === sectionId);
  if (!section) return;
  for (const u of updates) {
    const c = section.columns.find(col => col.id === u.columnId);
    if (c) c.weight = clampWeight(u.weight);
  }
}

/** Drag-resize a card's height (px). Heights below the minimum clamp to the minimum. */
export function setWidgetHeight(d: Draft<WorkspaceLayout>, widgetId: string, height: number | null): void {
  for (const s of d.sections) {
    for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === widgetId);
      if (w) {
        w.height = height === null ? null : Math.max(MIN_WIDGET_HEIGHT, Math.round(height));
        return;
      }
    }
  }
}

/** Merge a partial config into a widget instance (per-instance settings). */
export function setWidgetConfig(d: Draft<WorkspaceLayout>, widgetId: string, patch: Record<string, unknown>): void {
  for (const s of d.sections) {
    for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === widgetId);
      if (w) {
        w.config = { ...(w.config ?? {}), ...patch };
        return;
      }
    }
  }
}

/** Toggle a widget's hidden flag (kept in the layout, not rendered). */
export function toggleWidgetHidden(d: Draft<WorkspaceLayout>, widgetId: string): void {
  for (const s of d.sections) {
    for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === widgetId);
      if (w) {
        w.hidden = w.hidden ? undefined : true;
        return;
      }
    }
  }
}

/** Duplicate a widget instance, inserting the copy directly below the original. */
export function duplicateWidget(d: Draft<WorkspaceLayout>, widgetId: string): void {
  for (const s of d.sections) {
    for (const c of s.columns) {
      const idx = c.widgets.findIndex(x => x.id === widgetId);
      if (idx !== -1) {
        const src = c.widgets[idx];
        const copy: WidgetPlacement = {
          id: newId('wid'),
          widgetId: src.widgetId,
          height: src.height,
          config: src.config ? { ...src.config } : undefined,
          hidden: src.hidden,
        };
        c.widgets.splice(idx + 1, 0, copy);
        return;
      }
    }
  }
}

/**
 * Move a widget to the column immediately left or right of its current column
 * within the same section. If there is no adjacent column in that direction, a
 * new column is created beside the current one. The widget is appended to the
 * target column. This powers the "swap left/right" buttons in edit mode.
 */
export function moveWidgetToAdjacentColumn(d: Draft<WorkspaceLayout>, widgetId: string, direction: 'left' | 'right'): void {
  for (const s of d.sections) {
    const colIdx = s.columns.findIndex(c => c.widgets.some(w => w.id === widgetId));
    if (colIdx === -1) continue;
    const col = s.columns[colIdx];
    const widget = col.widgets.find(w => w.id === widgetId);
    if (!widget) return;
    // Remove the widget from its current column.
    col.widgets = col.widgets.filter(w => w.id !== widgetId);

    let targetIdx = direction === 'left' ? colIdx - 1 : colIdx + 1;
    if (targetIdx < 0 || targetIdx >= s.columns.length) {
      // No adjacent column — create one beside the current column.
      const fresh: WorkspaceColumn = { id: newId('col'), weight: 3, widgets: [] };
      const insertAt = direction === 'left' ? colIdx : colIdx + 1;
      s.columns.splice(insertAt, 0, fresh);
      targetIdx = insertAt;
    }
    s.columns[targetIdx].widgets.push(widget);
    pruneLayout(d);
    return;
  }
}

// ── Validation / migration / corrupt-read guard ──────────────────────────────

function asPlacement(raw: unknown, known?: ReadonlySet<string>): WidgetPlacement | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || !r.id || typeof r.widgetId !== 'string' || !r.widgetId) return null;
  if (known && !known.has(r.widgetId)) return null;
  const height = r.height;
  const defaultHeight = r.defaultHeight;
  const minHeight = r.minHeight;
  const config = r.config;
  return {
    id: r.id,
    widgetId: r.widgetId,
    height: typeof height === 'number' && Number.isFinite(height) ? height : null,
    defaultHeight: typeof defaultHeight === 'number' && Number.isFinite(defaultHeight) ? defaultHeight : undefined,
    minHeight: typeof minHeight === 'number' && Number.isFinite(minHeight) ? minHeight : undefined,
    config: typeof config === 'object' && config !== null && !Array.isArray(config) ? { ...(config as Record<string, unknown>) } : undefined,
    hidden: r.hidden === true ? true : undefined,
  };
}

/**
 * Repair an untrusted stored layout (any previous shape/version). Returns a
 * clean layout, or null when the payload is fundamentally unusable — callers
 * then fall back to defaults WITHOUT overwriting the stored data.
 */
export function normalizeLayout(raw: unknown, knownWidgetIds?: ReadonlySet<string>): WorkspaceLayout | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  // Accept both the current shape ({version, sections}) and legacy payloads
  // that are at least a {sections:[…]} tree; anything else is corrupt.
  if (!Array.isArray(r.sections) && !Array.isArray((r as { layout?: unknown }).layout)) return null;
  const sectionsRaw: unknown[] = Array.isArray(r.sections)
    ? r.sections
    : (r as { layout?: { sections?: unknown[] } }).layout?.sections ?? [];
  if (!Array.isArray(sectionsRaw)) return null;

  const seenWidgets = new Set<string>();
  const seenCols = new Set<string>();
  const seenSections = new Set<string>();
  const sections: WorkspaceSection[] = [];

  for (const sRaw of sectionsRaw) {
    if (typeof sRaw !== 'object' || sRaw === null) continue;
    const s = sRaw as Record<string, unknown>;
    if (!Array.isArray(s.columns)) continue;
    const columns: WorkspaceColumn[] = [];
    for (const cRaw of s.columns.slice(0, 4)) {
      if (typeof cRaw !== 'object' || cRaw === null) continue;
      const c = cRaw as Record<string, unknown>;
      if (!Array.isArray(c.widgets)) continue;
      const colId = typeof c.id === 'string' && c.id && !seenCols.has(c.id) ? c.id : newId('col');
      seenCols.add(colId);
      const widgets: WidgetPlacement[] = [];
      for (const wRaw of c.widgets) {
        const w = asPlacement(wRaw, knownWidgetIds);
        if (!w || seenWidgets.has(w.id)) continue;
        seenWidgets.add(w.id);
        widgets.push(w);
      }
      const weight = typeof c.weight === 'number' && Number.isFinite(c.weight)
        ? Math.max(MIN_COLUMN_WEIGHT, Math.min(MAX_COLUMN_WEIGHT, Math.round(c.weight * 10) / 10))
        : 3;
      columns.push({ id: colId, weight, widgets });
    }
    if (columns.length === 0) continue;
    const secId = typeof s.id === 'string' && s.id && !seenSections.has(s.id) ? s.id : newId('sec');
    seenSections.add(secId);
    // `rail` is the legacy name for `right` (two-zone era) — map it on read so
    // stored layouts survive the three-zone upgrade without a storage bump.
    const zone = s.zone === 'left' ? 'left' as const
      : s.zone === 'rail' || s.zone === 'right' ? 'right' as const
      : 'main' as const;
    sections.push({ id: secId, zone, columns: columns.slice(0, 4) });
  }

  if (sections.length === 0) return null;

  const hiddenZones = Array.isArray(r.hiddenZones)
    ? (r.hiddenZones as unknown[])
        .map(z => (z === 'left' ? 'left' : z === 'rail' || z === 'right' ? 'right' : null))
        .filter((z): z is 'left' | 'right' => z !== null)
    : undefined;

  const clampZoneWidth = (v: unknown): number | undefined => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return undefined;
    return Math.max(MIN_ZONE_WIDTH, Math.min(MAX_ZONE_WIDTH, Math.round(v)));
  };
  const rawWidths = (r.zoneWidths ?? {}) as Record<string, unknown>;
  const left = clampZoneWidth(rawWidths.left);
  const right = clampZoneWidth(rawWidths.right);
  const zoneWidths = (left != null || right != null) ? { ...(left != null ? { left } : {}), ...(right != null ? { right } : {}) } : undefined;

  return {
    version: WORKSPACE_VERSION,
    sections,
    ...(hiddenZones && hiddenZones.length > 0 ? { hiddenZones } : {}),
    ...(zoneWidths ? { zoneWidths } : {}),
  };
}