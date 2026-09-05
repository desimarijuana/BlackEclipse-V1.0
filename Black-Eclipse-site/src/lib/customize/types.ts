'use client';

// ── Customization kernel — shared types (layout schema v2) ──────────────────
// A page layout is a list of SECTIONS; each section has N columns (1–4) and
// holds one widget per column slot. This mirrors a visual builder (Elementor-
// style): users resize a section's column structure and drag widgets between
// sections/columns on the page itself.

export type Span = 1 | 2 | 3 | 4;
export type ColumnCount = 1 | 2 | 3 | 4;

export interface WidgetState {
  id: string;
  visible: boolean;
  /** Extra height in 40px steps (0 = natural). */
  height: number;
}

export interface Section {
  id: string;
  /** Number of equal columns in this section (1–4). */
  columns: ColumnCount;
  /** One widget per column slot; order = column order. Hidden widgets stay in
   * their slot but don't render. A section with 0 widgets is removed. */
  widgets: WidgetState[];
}

export interface PageLayout {
  version: 2;
  sections: Section[];
  presetId?: string;
}

export interface WidgetMeta {
  label: string;
  desc?: string;
  defaultSpan: Span;
  /** Extra default height in 40px steps. */
  defaultHeight?: number;
}

export interface PresetDefinition {
  id: string;
  name: string;
  desc: string;
  /** One bar per visual row — used by TemplateMiniGrid. */
  preview: Array<{ span: number; hidden?: boolean }>;
  /**
   * Section template: each entry is a section; tuple = [columnCount, ...widgetIds].
   * Widgets not listed are appended in a trailing "overflow" section (1 col).
   */
  sections: Array<[ColumnCount, ...string[]]>;
}

export interface PageDefinition {
  pageId: string;
  storageKey: string;
  widgets: Record<string, WidgetMeta>;
  /** Default widget order = Object.keys(widgets) order. */
  defaultOrder?: string[];
  presets: PresetDefinition[];
}

let sectionSeq = 0;
/** Fresh unique section id. */
export function newSectionId(): string {
  sectionSeq += 1;
  return `sec-${Date.now().toString(36)}-${sectionSeq}`;
}

/** Turn a PageDefinition's defaults into a fresh PageLayout (v2). */
export function defaultLayout(def: PageDefinition): PageLayout {
  const order = def.defaultOrder ?? Object.keys(def.widgets);
  const sections: Section[] = [];
  for (const id of order) {
    const meta = def.widgets[id];
    // Group widgets by defaultSpan: consecutive same-span widgets share a section.
    const span = meta.defaultSpan;
    // Map span → column layout: span4=1col, span3=3col(3/4-width feel), span2=2col, span1=4col.
    const last = sections[sections.length - 1];
    const spanCols: Record<Span, ColumnCount> = { 4: 1, 3: 3, 2: 2, 1: 4 };
    const want = spanCols[span];
    if (last && last.columns === want && last.widgets.length < want) {
      last.widgets.push({ id, visible: true, height: meta.defaultHeight ?? 0 });
    } else {
      sections.push({ id: newSectionId(), columns: want, widgets: [{ id, visible: true, height: meta.defaultHeight ?? 0 }] });
    }
  }
  return { version: 2, sections };
}

/** Build a PageLayout from a preset's section template. */
export function layoutFromPreset(def: PageDefinition, preset: PresetDefinition): PageLayout {
  const placed = new Set<string>();
  const sections: Section[] = [];
  for (const [cols, ...ids] of preset.sections) {
    const widgets: WidgetState[] = [];
    for (const id of ids) {
      if (!def.widgets[id] || placed.has(id)) continue;
      placed.add(id);
      widgets.push({ id, visible: true, height: def.widgets[id].defaultHeight ?? 0 });
    }
    if (widgets.length > 0) sections.push({ id: newSectionId(), columns: cols, widgets });
  }
  // Widgets not covered by the preset: append in a 1-col section each (or one
  // trailing multi-column section, matching their default span grouping).
  const order = def.defaultOrder ?? Object.keys(def.widgets);
  const rest = order.filter((id) => !placed.has(id));
  if (rest.length > 0) {
    sections.push({
      id: newSectionId(),
      columns: 1,
      widgets: rest.map((id) => ({ id, visible: true, height: def.widgets[id].defaultHeight ?? 0 })),
    });
  }
  return { version: 2, sections, presetId: preset.id };
}

// ── v1 → v2 migration ────────────────────────────────────────────────────────
/** v1 flat widget layout (legacy, pre-builder). */
export interface PageLayoutV1 {
  version?: 1;
  widgets: Array<{ id: string; visible: boolean; span: Span; height?: number }>;
}

/** Convert a flat v1 layout into sections: run-length group by span. */
export function migrateV1toV2(v1: PageLayoutV1): PageLayout {
  const sections: Section[] = [];
  for (const w of v1.widgets) {
    const spanCols: Record<Span, ColumnCount> = { 4: 1, 3: 3, 2: 2, 1: 4 };
    const cols = spanCols[w.span];
    const last = sections[sections.length - 1];
    if (last && last.columns === cols && last.widgets.length < cols) {
      last.widgets.push({ id: w.id, visible: w.visible, height: w.height ?? 0 });
    } else {
      sections.push({ id: newSectionId(), columns: cols, widgets: [{ id: w.id, visible: w.visible, height: w.height ?? 0 }] });
    }
  }
  return { version: 2, sections };
}

/** Normalize any stored layout (v1 or v2, possibly stale) into a valid v2. */
export function normalizeLayout(def: PageDefinition, stored: unknown): PageLayout {
  const base = defaultLayout(def);
  const known = new Set(Object.keys(def.widgets));
  if (!stored || typeof stored !== 'object') return base;
  const s = stored as { version?: number; widgets?: unknown; sections?: unknown };
  // v1 flat schema → migrate
  if (Array.isArray(s.widgets)) {
    const v1 = s as PageLayoutV1;
    if (!v1.widgets.every((w) => w && typeof w.id === 'string' && known.has(w.id))) return base;
    const migrated = migrateV1toV2(v1);
    appendUnknown(def, migrated, known);
    return migrated;
  }
  // v2 section schema → validate + merge unknown widgets
  if (Array.isArray(s.sections)) {
    const sections: Section[] = [];
    for (const raw of s.sections as Section[]) {
      if (!raw || typeof raw !== 'object' || !Array.isArray(raw.widgets)) continue;
      const widgets = raw.widgets
        .filter((w) => w && typeof w.id === 'string' && known.has(w.id))
        .map((w) => ({ id: w.id, visible: w.visible !== false, height: w.height ?? 0 }));
      if (widgets.length > 0) {
        sections.push({ id: raw.id ?? newSectionId(), columns: clampCols(raw.columns), widgets });
      }
    }
    const out: PageLayout = { version: 2, sections: sections.length ? sections : base.sections };
    appendUnknown(def, out, known);
    return out;
  }
  return base;
}

function appendUnknown(def: PageDefinition, layout: PageLayout, known: Set<string>): void {
  // Append widgets the stored layout never had (e.g. added in an app update)
  // into one trailing overflow section.
  const present = new Set(layout.sections.flatMap((s) => s.widgets.map((w) => w.id)));
  const missing = (def.defaultOrder ?? Object.keys(def.widgets)).filter((id) => !present.has(id) && known.has(id));
  if (missing.length === 0) return;
  layout.sections.push({
    id: newSectionId(),
    columns: 1,
    widgets: missing.map((id) => ({ id, visible: true, height: def.widgets[id].defaultHeight ?? 0 })),
  });
}

function clampCols(c: unknown): ColumnCount {
  return ([1, 2, 3, 4] as const).includes(c as ColumnCount) ? (c as ColumnCount) : 2;
}