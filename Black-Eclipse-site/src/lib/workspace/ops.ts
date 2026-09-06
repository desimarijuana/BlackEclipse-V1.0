// ── Pure layout operations (Immer drafts) ────────────────────────────────────
// Every function MUTATES the layout it is given and is meant to be invoked
// inside an Immer `produce` — copy-on-write makes that safe and keeps the
// result immutable for React. Nothing here touches the DOM or storage, so it
// is all unit-testable (tests wrap calls in `produce` and return the draft).

import {
  MAX_COLUMN_WEIGHT,
  MIN_COLUMN_WEIGHT,
  MIN_WIDGET_HEIGHT,
  newId,
  type DropTarget,
  type WorkspaceColumn,
  type WorkspaceLayout,
  type WorkspaceSection,
  type WidgetPlacement,
} from './types';
import type { Draft } from 'immer';

export function cloneLayout(l: WorkspaceLayout): WorkspaceLayout {
  return {
    version: 1,
    sections: l.sections.map(s => ({
      id: s.id,
      columns: s.columns.map(c => ({
        id: c.id,
        weight: c.weight,
        widgets: c.widgets.map(w => ({ ...w })),
      })),
    })),
  };
}

export function emptyLayout(): WorkspaceLayout {
  return {
    version: 1,
    sections: [{
      id: newId('sec'),
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
        columns: d.sections[0].columns.length > 0 ? d.sections[0].columns : [{ id: newId('col'), weight: 3, widgets: [] }],
      }];
    }
    return;
  }
  d.sections = nonEmpty.map(s => ({
    id: s.id,
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
 * at the end of the section. The index refers to positions AFTER removal of
 * the card from its origin (insertion index among the remaining siblings).
 */
export function moveWidget(d: Draft<WorkspaceLayout>, widgetId: string, target: DropTarget): void {
  const moved = takeWidget(d, widgetId);
  if (!moved) return;
  const column = draftColumn(d, target.sectionId, target.columnId);
  if (!column) { pruneLayout(d); return; }
  const index = Math.max(0, Math.min(target.index, column.widgets.length));
  column.widgets.splice(index, 0, moved);
  pruneLayout(d);
}

/** Move a card into a brand-new section (single column) appended at the end. */
export function moveWidgetToNewSection(d: Draft<WorkspaceLayout>, widgetId: string): void {
  const moved = takeWidget(d, widgetId);
  if (!moved) return;
  d.sections.push({ id: newId('sec'), columns: [{ id: newId('col'), weight: 3, widgets: [moved] }] });
  pruneLayout(d);
}

export function addWidget(d: Draft<WorkspaceLayout>, widgetId: string, target?: DropTarget): void {
  const widget: WidgetPlacement = { id: newId('wid'), widgetId, height: null };
  if (d.sections.length === 0) d.sections.push({ id: newId('sec'), columns: [] });

  let section = target ? d.sections.find(s => s.id === target.sectionId) : undefined;
  if (!section) section = d.sections[d.sections.length - 1];

  let column: Draft<WorkspaceColumn> | undefined;
  if (target && target.columnId === null) {
    // Explicit "new column" target.
    column = { id: newId('col'), weight: 3, widgets: [] };
    section.columns.push(column);
    column = section.columns[section.columns.length - 1];
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
  pruneLayout(d);
}

export function setColumnWeight(d: Draft<WorkspaceLayout>, columnId: string, weight: number): void {
  const clamped = Math.max(MIN_COLUMN_WEIGHT, Math.min(MAX_COLUMN_WEIGHT, Math.round(weight)));
  for (const s of d.sections) {
    const c = s.columns.find(col => col.id === columnId);
    if (c) { c.weight = clamped; return; }
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

// ── Validation / migration / corrupt-read guard ──────────────────────────────

function asPlacement(raw: unknown, known?: ReadonlySet<string>): WidgetPlacement | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || !r.id || typeof r.widgetId !== 'string' || !r.widgetId) return null;
  if (known && !known.has(r.widgetId)) return null;
  const height = r.height;
  return { id: r.id, widgetId: r.widgetId, height: typeof height === 'number' && Number.isFinite(height) ? height : null };
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
        ? Math.max(MIN_COLUMN_WEIGHT, Math.min(MAX_COLUMN_WEIGHT, Math.round(c.weight)))
        : 3;
      columns.push({ id: colId, weight, widgets });
    }
    if (columns.length === 0) continue;
    const secId = typeof s.id === 'string' && s.id && !seenSections.has(s.id) ? s.id : newId('sec');
    seenSections.add(secId);
    sections.push({ id: secId, columns: columns.slice(0, 4) });
  }

  if (sections.length === 0) return null;
  return { version: 1, sections };
}