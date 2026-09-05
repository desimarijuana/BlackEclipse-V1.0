'use client';

// ── Customization kernel — storage + layout ops (v3: Section → Column → Element) ─
// All ops are pure; persistence is a typed localStorage adapter.

import {
  newColumnId, newSectionId, normalizeLayout, defaultLayout,
  type Column, type ElementState, type ElementStyle, type PageDefinition, type PageLayout, type Section,
} from './types';

/** Load a page layout, upgrading v1/v2 → v3 and merging unknown widgets. */
export function loadLayout(def: PageDefinition): PageLayout {
  if (typeof window === 'undefined') return defaultLayout(def);
  try {
    const raw = window.localStorage.getItem(def.storageKey);
    if (!raw) {
      // Legacy keys: try the pre-versioned base name (eclipse_portfolio_layout)
      // and intermediate _v2 names, normalizing whatever we find.
      const candidates = [
        def.storageKey.replace(/_v\d+$/, ''),
        def.storageKey.replace(/_v3$/, '_v2'),
      ].filter((k) => k !== def.storageKey);
      for (const key of candidates) {
        const legacyRaw = window.localStorage.getItem(key);
        if (legacyRaw) return normalizeLayout(def, JSON.parse(legacyRaw));
      }
      return defaultLayout(def);
    }
    return normalizeLayout(def, JSON.parse(raw));
  } catch {
    return defaultLayout(def);
  }
}

export function saveLayout(def: PageDefinition, layout: PageLayout): void {
  try { window.localStorage.setItem(def.storageKey, JSON.stringify(layout)); } catch { /* private mode */ }
}

export function clearLayout(def: PageDefinition): void {
  try { window.localStorage.removeItem(def.storageKey); } catch { /* ignore */ }
}

/** Deep-clone a layout (pure-op helper). */
export function cloned(layout: PageLayout): PageLayout {
  return {
    ...layout,
    sections: layout.sections.map((s) => ({
      ...s,
      columns: s.columns.map((c) => ({ ...c, elements: c.elements.map((e) => ({ ...e, style: { ...e.style } })) })),
    })),
  };
}

/** All elements in order (Navigator + add-widget lists). */
export function allElements(layout: PageLayout): ElementState[] {
  return layout.sections.flatMap((s) => s.columns.flatMap((c) => c.elements));
}

export function elementIds(layout: PageLayout): string[] {
  return allElements(layout).map((e) => e.id);
}

/** Locate an element: returns its state, column, section and indices. */
export function locate(layout: PageLayout, elementId: string): {
  element: ElementState; column: Column; section: Section;
  colIdx: number; elIdx: number; secIdx: number;
} | null {
  for (let si = 0; si < layout.sections.length; si++) {
    const section = layout.sections[si];
    for (let ci = 0; ci < section.columns.length; ci++) {
      const column = section.columns[ci];
      const elIdx = column.elements.findIndex((e) => e.id === elementId);
      if (elIdx !== -1) {
        return { element: column.elements[elIdx], column, section, colIdx: ci, elIdx, secIdx: si };
      }
    }
  }
  return null;
}

/** Patch one element (style or visibility) — pure. */
export function patched(layout: PageLayout, id: string, patch: Partial<Omit<ElementState, 'id' | 'style'>> & { style?: Partial<ElementStyle> }): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) {
    for (const c of s.columns) {
      for (const e of c.elements) {
        if (e.id === id) {
          if (patch.visible !== undefined) e.visible = patch.visible;
          if (patch.style) Object.assign(e.style, patch.style);
        }
      }
    }
  }
  return next;
}

/** Patch section-level layout styling. */
export function patchSection(layout: PageLayout, sectionId: string, patch: Partial<Pick<Section, 'gap' | 'padding'>>): PageLayout {
  const next = cloned(layout);
  const s = next.sections.find((x) => x.id === sectionId);
  if (s) Object.assign(s, patch);
  return next;
}

/** Set a section's column count, redistributing elements (row-major fill). */
export function setColumnCount(layout: PageLayout, sectionId: string, count: 1 | 2 | 3 | 4): PageLayout {
  const next = cloned(layout);
  const s = next.sections.find((x) => x.id === sectionId);
  if (!s) return layout;
  const flat = s.columns.flatMap((c) => c.elements);
  const columns: Column[] = Array.from({ length: count }, (_, i) => ({
    id: i < s.columns.length ? s.columns[i].id : newColumnId(),
    width: 1,
    elements: [],
  }));
  flat.forEach((el, i) => columns[i % count].elements.push(el));
  s.columns = columns;
  return pruneSections(next);
}

/** Set one column's relative width share (auto-normalized in the renderer). */
export function setColumnWidth(layout: PageLayout, columnId: string, width: 1 | 2 | 3 | 4): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) {
    const col = s.columns.find((c) => c.id === columnId);
    if (col) { col.width = width; break; }
  }
  return next;
}

/**
 * Place an element at a precise position: section + column + element index.
 * `elementIdx` null = append to the column's end.
 */
export function placeElement(
  layout: PageLayout,
  elementId: string,
  target: { sectionId: string; columnId: string; elementIdx: number | null },
): PageLayout {
  // Find & detach the element (pure on the clone)
  const src = locate(layout, elementId);
  if (!src) return layout;
  const next = cloned(layout);
  const detached = next.sections[src.secIdx].columns[src.colIdx].elements.splice(src.elIdx, 1)[0];
  // Prune any columns/sections emptied by the removal (but not the target)
  const targetStillExists = next.sections.some((s) => s.id === target.sectionId && s.columns.some((c) => c.id === target.columnId));
  for (const s of next.sections) {
    s.columns = s.columns.filter((c) => c.elements.length > 0 || (s.id === target.sectionId && c.id === target.columnId && targetStillExists));
  }
  next.sections = next.sections.filter((s) => s.columns.length > 0);

  // Re-find target on the mutated tree (ids survive pruning unless it was emptied)
  const tSec = next.sections.find((s) => s.id === target.sectionId);
  if (!tSec) {
    // Target section vanished → recreate with the element
    next.sections.push({ id: target.sectionId, gap: 16, padding: 'none', columns: [{ id: target.columnId ?? newColumnId(), width: 1, elements: [detached] }] });
    return next;
  }
  let tCol = tSec.columns.find((c) => c.id === target.columnId);
  if (!tCol) {
    tCol = { id: target.columnId ?? newColumnId(), width: 1, elements: [] };
    tSec.columns.push(tCol);
  }
  if (target.elementIdx === null || target.elementIdx >= tCol.elements.length) {
    tCol.elements.push(detached);
  } else {
    tCol.elements.splice(Math.max(0, target.elementIdx), 0, detached);
  }
  return next;
}

/** Move an element by ±1 slot within its column; falls back to neighbouring column. */
export function nudged(layout: PageLayout, id: string, dir: -1 | 1): PageLayout {
  const loc = locate(layout, id);
  if (!loc) return layout;
  const next = cloned(layout);
  const col = next.sections[loc.secIdx].columns[loc.colIdx];
  const j = loc.elIdx + dir;
  if (j >= 0 && j < col.elements.length) {
    const [m] = col.elements.splice(loc.elIdx, 1);
    col.elements.splice(j, 0, m);
    return next;
  }
  // At column edge → move into neighbouring column (append at the entry side)
  const section = next.sections[loc.secIdx];
  const targetColIdx = loc.colIdx + dir;
  if (targetColIdx < 0 || targetColIdx >= section.columns.length) return layout;
  const [m] = col.elements.splice(loc.elIdx, 1);
  if (col.elements.length === 0) section.columns.splice(loc.colIdx, 1);
  const tCol = section.columns[Math.min(targetColIdx, section.columns.length - 1)];
  if (dir === 1) tCol.elements.unshift(m);
  else tCol.elements.push(m);
  return pruneSections(next);
}

/** Add a widget (from the library) into a column — or a new trailing section. */
export function addElement(layout: PageLayout, def: PageDefinition, widgetId: string, columnId: string | null): PageLayout {
  if (!def.widgets[widgetId]) return layout;
  if (elementIds(layout).includes(widgetId)) return layout; // single instance per page
  const next = cloned(layout);
  const el: ElementState = {
    id: widgetId, visible: true,
    style: { height: 0, width: 'auto', padding: 'none', align: 'stretch' },
  };
  if (columnId) {
    for (const s of next.sections) {
      const col = s.columns.find((c) => c.id === columnId);
      if (col) { col.elements.push(el); return next; }
    }
  }
  next.sections.push({ id: newSectionId(), gap: 16, padding: 'none', columns: [{ id: newColumnId(), width: 1, elements: [el] }] });
  return next;
}

/** Remove an element back to the hidden library. */
export function removeElement(layout: PageLayout, elementId: string): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) for (const c of s.columns) c.elements = c.elements.filter((e) => e.id !== elementId);
  return pruneSections(next);
}

/** Drop columns/sections with no elements. */
export function pruneSections(layout: PageLayout): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) s.columns = s.columns.filter((c) => c.elements.length > 0);
  next.sections = next.sections.filter((s) => s.columns.length > 0);
  return next;
}