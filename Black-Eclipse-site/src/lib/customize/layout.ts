'use client';

// ── Customization kernel — storage + layout ops (section model) ─────────────
// All ops are pure; persistence is a typed localStorage adapter.

import {
  newSectionId, normalizeLayout, defaultLayout,
  type ColumnCount, type PageDefinition, type PageLayout, type Section, type WidgetState,
} from './types';

/** Load a page layout, upgrading v1 → v2 and merging unknown widgets.
 * Falls back to the legacy (v1-era) storage key when the primary is absent. */
export function loadLayout(def: PageDefinition): PageLayout {
  if (typeof window === 'undefined') return defaultLayout(def);
  try {
    const raw = window.localStorage.getItem(def.storageKey);
    if (!raw) {
      // Legacy key: same key with a `_layout`→`_layout` name is already primary;
      // historical v1 keys used the pre-builder names.
      const legacyKey = def.storageKey.replace('_v2', '');
      const legacyRaw = legacyKey !== def.storageKey ? window.localStorage.getItem(legacyKey) : null;
      if (legacyRaw) return normalizeLayout(def, JSON.parse(legacyRaw));
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
  return { ...layout, sections: layout.sections.map((s) => ({ ...s, widgets: s.widgets.map((w) => ({ ...w })) })) };
}

/** All widgets in order (for panel/Navigator + add-widget lists). */
export function allWidgets(layout: PageLayout): WidgetState[] {
  return layout.sections.flatMap((s) => s.widgets);
}

/** Patch one widget (any section) — returns next layout (pure). */
export function patched(layout: PageLayout, id: string, patch: Partial<Omit<WidgetState, 'id'>>): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) {
    for (const w of s.widgets) {
      if (w.id === id) Object.assign(w, patch);
    }
  }
  return next;
}

/** Set a section's column count, reflowing widgets across the new slots. */
export function setSectionColumns(layout: PageLayout, sectionId: string, columns: ColumnCount): PageLayout {
  const next = cloned(layout);
  const s = next.sections.find((x) => x.id === sectionId);
  if (!s) return layout;
  if (columns >= s.widgets.length) {
    s.columns = columns;
    return next;
  }
  // Too many widgets for fewer columns: overflow into a new section after.
  const keep = s.widgets.slice(0, columns);
  const overflow = s.widgets.slice(columns);
  s.columns = columns;
  s.widgets = keep;
  const idx = next.sections.indexOf(s);
  next.sections.splice(idx + 1, 0, { id: newSectionId(), columns, widgets: overflow });
  return next;
}

/** Move a widget to a target position: before widget `beforeId` in section
 * `sectionId` (or appended when beforeId is null). Cross-section safe. */
export function placeWidget(
  layout: PageLayout,
  widgetId: string,
  sectionId: string,
  beforeId: string | null,
): PageLayout {
  // Remove from source
  const src = layout.sections.find((s) => s.widgets.some((w) => w.id === widgetId));
  const widget = src?.widgets.find((w) => w.id === widgetId);
  if (!widget) return layout;

  const next = cloned(layout);
  const sNext = next.sections.find((x) => x.id === sectionId);
  if (!sNext) return layout;

  // Same section & same position → no-op
  if (src?.id === sectionId) {
    const i = sNext.widgets.findIndex((w) => w.id === widgetId);
    const targetIdx = beforeId ? sNext.widgets.findIndex((w) => w.id === beforeId) : sNext.widgets.length;
    if (i === targetIdx || (targetIdx === sNext.widgets.length && i === sNext.widgets.length - 1)) return layout;
  }

  // Remove from source, prune empty sections (except if it IS the target and would empty)
  const srcNext = next.sections.find((x) => x.id === src!.id)!;
  srcNext.widgets = srcNext.widgets.filter((w) => w.id !== widgetId);
  if (srcNext.widgets.length === 0 && srcNext.id !== sectionId) {
    next.sections = next.sections.filter((s) => s.id !== srcNext.id);
  }

  // Insert into target
  const target = next.sections.find((x) => x.id === sectionId)!;
  const at = beforeId ? target.widgets.findIndex((w) => w.id === beforeId) : -1;
  if (beforeId && at !== -1) target.widgets.splice(at, 0, widget);
  else target.widgets.push(widget);

  // If target now overfull, grow its columns to fit
  if (target.widgets.length > target.columns) {
    target.columns = Math.min(4, target.widgets.length) as ColumnCount;
  }
  return next;
}

/** Append a widget into a section (or a new trailing section when null). */
export function addWidget(layout: PageLayout, def: PageDefinition, widgetId: string, sectionId: string | null): PageLayout {
  if (!def.widgets[widgetId]) return layout;
  if (allWidgets(layout).some((w) => w.id === widgetId)) return layout; // already placed
  const next = cloned(layout);
  const w: WidgetState = { id: widgetId, visible: true, height: def.widgets[widgetId].defaultHeight ?? 0 };
  if (sectionId) {
    const s = next.sections.find((x) => x.id === sectionId);
    if (s) {
      s.widgets.push(w);
      if (s.widgets.length > s.columns) s.columns = Math.min(4, s.widgets.length) as ColumnCount;
      return next;
    }
  }
  next.sections.push({ id: newSectionId(), columns: 1, widgets: [w] });
  return next;
}

/** Remove a widget from the layout (returns to the hidden library). */
export function removeWidget(layout: PageLayout, widgetId: string): PageLayout {
  const next = cloned(layout);
  for (const s of next.sections) s.widgets = s.widgets.filter((w) => w.id !== widgetId);
  next.sections = next.sections.filter((s) => s.widgets.length > 0);
  return next;
}

/** Nudge a widget within its section by ±1 column slot. */
export function nudged(layout: PageLayout, id: string, dir: -1 | 1): PageLayout {
  const next = cloned(layout);
  const s = next.sections.find((x) => x.widgets.some((w) => w.id === id));
  if (!s) return layout;
  const i = s.widgets.findIndex((w) => w.id === id);
  const j = i + dir;
  if (j < 0 || j >= s.widgets.length) return layout;
  const [m] = s.widgets.splice(i, 1);
  s.widgets.splice(j, 0, m);
  return next;
}

/** Delete an empty section by id (pure). */
export function pruneSections(layout: PageLayout): PageLayout {
  const next = cloned(layout);
  next.sections = next.sections.filter((s) => s.widgets.length > 0);
  return next;
}

/** Sections list helper for consumers. */
export function sectionsOf(layout: PageLayout): Section[] {
  return layout.sections;
}