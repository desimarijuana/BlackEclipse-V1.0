# CUSTOMIZE.md — Customization System Patterns

> Read this before adding a customizable page, widget, or preset.
> The customization kernel lives in `src/lib/customize/` — screens must **register, not hand-roll**.

---

## Core rule

Every customizable page uses the shared kernel with the **section → column → element model**
(Elementor-style). Never write page-local layout state, localStorage code, drag plumbing,
or structure-picker UI.

```
src/lib/customize/
  types.ts       — ElementState { id, visible, style: ElementStyle }, Column { id, width, elements[] },
                   Section { id, gap, padding, columns[] }, PageLayout v3, PageDefinition,
                   PresetDefinition (section templates), defaultLayout(), layoutFromPreset(),
                   migrateV1toV3(), migrateV2toV3(), normalizeLayout()
  layout.ts      — load/save/clear + pure ops: patched (element style/visibility),
                   patchSection (gap/padding), setColumnCount (redistributes row-major),
                   setColumnWidth, placeElement (section/column/index — cross-section),
                   nudged, addElement, removeElement, pruneSections, locate
  use-customize.ts — useCustomize(def): { layout, widgets, visible, patch, patchSec, place,
                   setColumns, setColWidth, add, remove, nudge, applyPreset, apply, reset }
  components.tsx — StructurePicker, SectionSpacingPicker, ColumnWidthPicker,
                   ElementStylePicker, SectionShell, ColumnShell, ElementShell
  coach-mark.tsx — one-time "press Customize" hint per page
  fund-page-def.ts — fund page PageDefinition (reference example)
  customize.test.ts — 16 unit tests for schema/migration/ops (keep green)
```

## Layout schema v3 (Section → Column → Element)

```ts
interface Section   { id; gap: 0|8|16|24; padding: 'none'|'sm'|'md'; columns: Column[] }
interface Column    { id; width: 1|2|3|4; elements: ElementState[] }   // elements STACK inside a column
interface ElementState { id; visible; style: ElementStyle }            // style is per-element
interface ElementStyle { height; width: 'auto'|1|2|3|4; padding: 'none'|'sm'|'md'; align }
interface PageLayout{ version: 3; sections: Section[]; presetId? }
```

- **v1 (flat) and v2 (one-widget-per-slot) layouts auto-upgrade**; unknown/stale ids are dropped,
  missing widgets appended. Storage keys: `eclipse_<page>_layout_v3`; `loadLayout` falls back to
  legacy keys automatically.
- **Columns** have individual width shares (×1–×4, flex-grown) — not all sections must be equal.
- **Elements** are independent components stacked in a column; many per column. Their styling
  (width/height/padding/align) is separate from section/column layout styling.
- **Element toolbars** (⚙ icon on hover) customize width %, min-height, inner padding, alignment.
- **Section toolbars** customize column count + gap + padding. **Column toolbars** set width share.
- Drag & drop: grab any element card → drop on a column (append) or another element (insert
  before); cross-section moves prune emptied columns/sections.
- Navigator panel is a **view-only tree** — all manipulation happens on the canvas.

## Adding a customizable page (checklist)

1. Widget meta map: `Record<WidgetId, WidgetMeta>` (`label`, `desc?`, `defaultSpan`).
2. Presets as **section templates**: `sections: [{ widths: [1,1], elements: ['a','b'] }, ...]`.
   Elements beyond the listed columns stack into the last column; unlisted widgets append in a
   trailing overflow section.
3. `PageDefinition`: `{ pageId, storageKey: 'eclipse_<page>_layout_v3', widgets, presets }`.
4. In the screen: `const c = useCustomize(MY_PAGE);`
5. Render the canvas:
   - `layout.sections.map` → `<SectionShell editing gap padding onSpacing onColumns onDelete>`
     (columns = `section.columns.length`).
   - Inside: `<div className="flex flex-col md:flex-row ${SECTION_GAP_CLASS[section.gap]}">`
     mapping `section.columns` → `<ColumnShell editing width onWidth elementCount dragging
     onDropInColumn>` (ColumnShell applies the flex-grow).
   - Inside: `<div className="flex flex-col ${SECTION_GAP_CLASS[section.gap]}">` mapping
     `col.elements` → `<ElementShell editing label style onStyle visible onToggleVisible
     dragging dragOver onDragStart onDragEnd onDragOverElement onDropOnElement>` — drop index =
     element's position in `col.elements`.
   - Element style on the wrapper: `ELEM_PAD_CLASS[style.padding]` +
     `ELEM_ALIGN_CLASS[style.align]` + width/minHeight inline styles (ElementShell non-edit
     branch shows the pattern).
   - **Panel (Navigator)**: view-only tree — sections → columns → element chips with eye
     toggles + StructurePicker per section. No dragging here.
6. Keep grid classes as static strings only where still needed; the v3 model uses flex,
   so no `lg:grid-cols-*` maps are required.

## Interactions (must match everywhere)

- **Columns**: hover a section → StructurePicker → 1/2/3/4 columns; elements redistribute
  row-major (`setColumnCount`).
- **Column width**: hover a column → `ColumnWidthPicker` (×1–×4 flex share).
- **Element style**: hover an element → ⚙ → width (Fill/25/50/75/100%), min-height ±40px,
  inner padding, alignment.
- **Section spacing**: hover a section → maximize icon → gap (0/8/16/24px) + padding.
- **Move**: drag any element card → column (append) or another element (insert-before).
- **Visibility**: eye toggle on the element toolbar; hidden elements show a dashed overlay
  while editing and disappear otherwise.
- **Presets** apply a full section template in one click.

## Conventions & anti-patterns

- Widget ids are stable strings — renaming requires a storage migration in `layout.ts`.
- Keep widget render logic in the screen; the kernel owns only layout state.
- Toolbars use **opacity-based hover reveal** (`opacity-0 group-hover/*:opacity-100
  pointer-events-none group-hover/*:pointer-events-auto`), NOT `hidden ... :flex` — so
  automation and keyboard users can reach them.
- Never hand-roll a second picker or panel style; reuse the kernel components so every page
  feels identical.
- Never store layouts in an untyped shape — always `PageLayout` via the kernel.