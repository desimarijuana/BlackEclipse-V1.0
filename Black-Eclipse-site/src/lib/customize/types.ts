'use client';

// ── Customization kernel — shared types (layout schema v3) ──────────────────
// True Elementor-style 3-level model:
//   Section → Columns[] (each with an individual width share) → Elements[]
// Elements are independent components stacked INSIDE a column; a column can
// hold any number of elements. Element styling is separate from column/layout
// styling (element state carries its own style fields).

export type Span = 1 | 2 | 3 | 4;

/** Per-element customization (kept separate from column/layout styling). */
export interface ElementStyle {
  /** Extra min-height in 40px steps (0 = natural). */
  height: number;
  /** Width fill within its column: 'auto' (fill) | 1–4 blocks of the column. */
  width: 'auto' | Span;
  /** Inner padding: none | sm | md (applies to the element wrapper). */
  padding: 'none' | 'sm' | 'md';
  /** Horizontal alignment inside the column. */
  align: 'stretch' | 'start' | 'center' | 'end';
}

export interface ElementState {
  /** Widget id (unique per page — one instance of each widget). */
  id: string;
  visible: boolean;
  style: ElementStyle;
}

export interface Column {
  id: string;
  /** Relative width share vs sibling columns (default 1 = equal). 1–4. */
  width: 1 | 2 | 3 | 4;
  /** Elements stacked vertically inside this column, in order. */
  elements: ElementState[];
}

export interface Section {
  id: string;
  columns: Column[];
  /** Inner spacing between columns in px steps: 0 | 8 | 16 | 24. */
  gap: 0 | 8 | 16 | 24;
  /** Vertical padding of the section: none | sm | md. */
  padding: 'none' | 'sm' | 'md';
}

export interface PageLayout {
  version: 3;
  sections: Section[];
  presetId?: string;
}

export interface WidgetMeta {
  label: string;
  desc?: string;
  /** Preferred column count when auto-grouping into a fresh layout. */
  defaultSpan: Span;
}

export interface PresetDefinition {
  id: string;
  name: string;
  desc: string;
  /** One bar per visual row — used by TemplateMiniGrid. */
  preview: Array<{ span: number; hidden?: boolean }>;
  /**
   * Section template: [columnWidths[], ...elementIds] per section.
   * e.g. [[1,1], 'a', 'b'] = section with two equal columns holding a and b.
   * Elements beyond the listed columns stack into the last column.
   */
  sections: Array<{ widths: number[]; elements: string[] }>;
}

export interface PageDefinition {
  pageId: string;
  storageKey: string;
  widgets: Record<string, WidgetMeta>;
  defaultOrder?: string[];
  presets: PresetDefinition[];
}

let seq = 0;
/** Fresh unique id with a namespace prefix. */
export function newId(prefix: string): string {
  seq += 1;
  return `${prefix}-${Date.now().toString(36)}-${seq}`;
}
export const newSectionId = () => newId('sec');
export const newColumnId = () => newId('col');

function defaultStyle(): ElementStyle {
  return { height: 0, width: 'auto', padding: 'none', align: 'stretch' };
}

function makeElement(id: string, def: PageDefinition): ElementState {
  void def;
  return { id, visible: true, style: defaultStyle() };
}

/** Divide n columns' width shares. Equal by default. */
function equalColumns(n: number, elements: ElementState[]): Column[] {
  const widths = Array.from({ length: n }, () => 1 as const);
  return widths.map((w, i) => ({ id: newColumnId(), width: w, elements: i === 0 ? elements : [] }));
}

/** Turn a PageDefinition's defaults into a fresh PageLayout (v3). */
export function defaultLayout(def: PageDefinition): PageLayout {
  const order = def.defaultOrder ?? Object.keys(def.widgets);
  const sections: Section[] = [];
  const spanCols: Record<Span, number> = { 4: 1, 3: 3, 2: 2, 1: 4 };
  let want = 0;
  for (const id of order) {
    const cols = spanCols[def.widgets[id].defaultSpan];
    const last = sections[sections.length - 1];
    if (last && want === cols && last.columns.length < cols) {
      // Same-span run → one column per widget until the section is full.
      last.columns.push({ id: newColumnId(), width: 1, elements: [makeElement(id, def)] });
    } else {
      want = cols;
      sections.push({ id: newSectionId(), gap: 16, padding: 'none', columns: [{ id: newColumnId(), width: 1, elements: [makeElement(id, def)] }] });
    }
  }
  return { version: 3, sections };
}

/** Build a PageLayout from a preset's section template. */
export function layoutFromPreset(def: PageDefinition, preset: PresetDefinition): PageLayout {
  const placed = new Set<string>();
  const sections: Section[] = [];
  for (const tpl of preset.sections) {
    const n = Math.max(1, tpl.widths.length);
    const columns: Column[] = Array.from({ length: n }, (_, i) => ({
      id: newColumnId(),
      width: (Math.max(1, Math.min(4, tpl.widths[i] ?? 1))) as 1 | 2 | 3 | 4,
      elements: [],
    }));
    // Distribute elements round-robin across columns; extras stack in the last.
    tpl.elements.forEach((id, idx) => {
      if (!def.widgets[id] || placed.has(id)) return;
      placed.add(id);
      const col = columns[Math.min(idx, n - 1)];
      col.elements.push(makeElement(id, def));
    });
    const nonEmpty = columns.filter((c) => c.elements.length > 0);
    if (nonEmpty.length > 0) {
      sections.push({ id: newSectionId(), gap: 16, padding: 'none', columns: nonEmpty });
    }
  }
  // Widgets not covered by the preset: one trailing single-column section.
  const order = def.defaultOrder ?? Object.keys(def.widgets);
  const rest = order.filter((id) => !placed.has(id));
  if (rest.length > 0) {
    sections.push({
      id: newSectionId(),
      gap: 16,
      padding: 'none',
      columns: equalColumns(1, rest.map((id) => makeElement(id, def))),
    });
  }
  return { version: 3, sections, presetId: preset.id };
}

// ── v2 (one-widget-per-slot sections) & v1 (flat) → v3 migration ────────────
/** v2 stored shape: sections with `columns: number` + `widgets[]`. */
export interface PageLayoutV2 {
  version?: 2;
  sections: Array<{ id?: string; columns: number; widgets: Array<{ id: string; visible: boolean; height?: number }> }>;
}

/** v1 flat shape. */
export interface PageLayoutV1 {
  version?: 1;
  widgets: Array<{ id: string; visible: boolean; span: Span; height?: number }>;
}

export function migrateV1toV3(v1: PageLayoutV1): PageLayout {
  const sections: Section[] = [];
  const spanCols: Record<Span, number> = { 4: 1, 3: 3, 2: 2, 1: 4 };
  for (const w of v1.widgets) {
    const want = spanCols[w.span];
    const last = sections[sections.length - 1];
    const lastCol = last?.columns[0];
    if (last && last.columns.length === 1 && lastCol && lastCol.elements.length > 0 &&
        spanCols[0 as Span] === want) { // span info lost per-element; group by same span is impossible → new section per widget
      lastCol.elements.push({ id: w.id, visible: w.visible, style: { height: w.height ?? 0, width: 'auto', padding: 'none', align: 'stretch' } });
    } else {
      sections.push({ id: newSectionId(), gap: 16, padding: 'none', columns: equalColumns(1, [
        { id: w.id, visible: w.visible, style: { height: w.height ?? 0, width: 'auto', padding: 'none', align: 'stretch' } },
      ]) });
    }
  }
  return { version: 3, sections };
}

export function migrateV2toV3(v2: PageLayoutV2): PageLayout {
  const sections: Section[] = [];
  for (const raw of v2.sections) {
    const n = Math.max(1, Math.min(4, raw.columns || 1));
    const valid = raw.widgets.filter((w) => w && typeof w.id === 'string');
    // Distribute the old one-widget-per-slot rows across n columns.
    const columns: Column[] = Array.from({ length: n }, (_, i) => ({
      id: newColumnId(),
      width: 1,
      elements: valid
        .filter((_, idx) => idx % n === i)
        .map((w) => ({ id: w.id, visible: w.visible !== false, style: { height: w.height ?? 0, width: 'auto', padding: 'none', align: 'stretch' } })),
    }));
    const nonEmpty = columns.filter((c) => c.elements.length > 0);
    if (nonEmpty.length > 0) sections.push({ id: raw.id ?? newSectionId(), gap: 16, padding: 'none', columns: nonEmpty });
  }
  return { version: 3, sections };
}

/** Normalize any stored layout (v1, v2, or v3) into a valid v3. */
export function normalizeLayout(def: PageDefinition, stored: unknown): PageLayout {
  const base = defaultLayout(def);
  const known = new Set(Object.keys(def.widgets));
  if (!stored || typeof stored !== 'object') return base;
  const s = stored as { version?: number; widgets?: unknown; sections?: unknown };
  // v1 flat
  if (Array.isArray(s.widgets)) {
    const v1 = s as PageLayoutV1;
    if (!v1.widgets.every((w) => w && typeof w.id === 'string' && known.has(w.id))) return base;
    const out = migrateV1toV3(v1);
    appendUnknown(def, out, known);
    return out;
  }
  // v2 sections-with-count or v3 sections-with-columns
  if (Array.isArray(s.sections)) {
    const sections: Section[] = [];
    for (const raw of s.sections as Array<Record<string, unknown>>) {
      if (!raw || typeof raw !== 'object') continue;
      // v3: raw.columns is an array of column objects
      if (Array.isArray(raw.columns) && typeof raw.columns[0] === 'object' && raw.columns[0] !== null && 'elements' in (raw.columns[0] as object)) {
        const columns: Column[] = (raw.columns as Array<Record<string, unknown>>)
          .map((c) => ({
            id: typeof c.id === 'string' ? c.id : newColumnId(),
            width: (Math.max(1, Math.min(4, typeof c.width === 'number' ? c.width : 1))) as 1 | 2 | 3 | 4,
            elements: (Array.isArray(c.elements) ? c.elements : [])
              .filter((e) => e && typeof (e as ElementState).id === 'string' && known.has((e as ElementState).id))
              .map((e) => {
                const el = e as Partial<ElementState>;
                return {
                  id: el.id as string,
                  visible: el.visible !== false,
                  style: {
                    height: typeof el.style?.height === 'number' ? el.style.height : 0,
                    width: el.style?.width === 'auto' || (typeof el.style?.width === 'number' && el.style.width >= 1 && el.style.width <= 4) ? el.style.width : 'auto',
                    padding: el.style?.padding === 'none' || el.style?.padding === 'sm' || el.style?.padding === 'md' ? el.style.padding : 'none',
                    align: el.style?.align === 'start' || el.style?.align === 'center' || el.style?.align === 'end' ? el.style.align : 'stretch',
                  } as ElementStyle,
                };
              }),
          }))
          .filter((c) => c.elements.length > 0);
        if (columns.length > 0) {
          sections.push({
            id: typeof raw.id === 'string' ? raw.id : newSectionId(),
            gap: (raw.gap === 0 || raw.gap === 8 || raw.gap === 24 ? raw.gap : 16) as Section['gap'],
            padding: raw.padding === 'sm' || raw.padding === 'md' ? raw.padding : 'none',
            columns,
          });
        }
        continue;
      }
      // v2: raw.columns is a number + raw.widgets array
      if (typeof raw.columns === 'number' && Array.isArray(raw.widgets)) {
        const v2sec = { columns: raw.columns, widgets: raw.widgets as PageLayoutV2['sections'][number]['widgets'], id: raw.id as string | undefined };
        const migrated = migrateV2toV3({ sections: [v2sec] });
        sections.push(...migrated.sections);
      }
    }
    if (sections.length > 0) {
      const out: PageLayout = { version: 3, sections };
      appendUnknown(def, out, known);
      return out;
    }
    return base;
  }
  return base;
}

function appendUnknown(def: PageDefinition, layout: PageLayout, known: Set<string>): void {
  const present = new Set(allElementIds(layout));
  const missing = (def.defaultOrder ?? Object.keys(def.widgets)).filter((id) => !present.has(id) && known.has(id));
  if (missing.length === 0) return;
  layout.sections.push({
    id: newSectionId(),
    gap: 16,
    padding: 'none',
    columns: equalColumns(1, missing.map((id) => makeElement(id, def))),
  });
}

/** Collect every element id in the layout (in order). */
export function allElementIds(layout: PageLayout): string[] {
  return layout.sections.flatMap((s) => s.columns.flatMap((c) => c.elements.map((e) => e.id)));
}

// (clampCols/ColumnCount kept for potential legacy consumers — currently unused.)