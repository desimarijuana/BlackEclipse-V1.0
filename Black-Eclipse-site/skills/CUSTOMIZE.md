# CUSTOMIZE.md — Customization System Patterns

> Read this before adding a customizable page, widget, or preset.
> The customization kernel lives in `src/lib/customize/` — screens must **register, not hand-roll**.

---

## Core rule

Every customizable page uses the shared kernel with the **section layout model** (Elementor-style):
a page is a list of **sections**, each section has **1–4 columns**, and each column holds one widget.
Never write page-local layout state, localStorage code, drag plumbing, or structure-picker UI.

```
src/lib/customize/
  types.ts       — WidgetState, Section { columns, widgets }, PageLayout v2,
                   PageDefinition, PresetDefinition (section templates),
                   defaultLayout(), layoutFromPreset(), migrateV1toV2(), normalizeLayout()
  layout.ts      — load/save/clear + pure ops: patched, placeWidget (cross-section move),
                   setSectionColumns (reflows overflow), addWidget, removeWidget, nudged
  use-customize.ts — useCustomize(def): { layout, widgets, visible, patch, place,
                   setColumns, add, remove, nudge, applyPreset, apply, reset }
  components.tsx — StructurePicker (column presets popover), SectionShell (hover frame +
                   toolbar), WidthPicker, SPAN_CLASS, TemplateMiniGrid
  coach-mark.tsx — one-time "press Customize" hint per page
  fund-page-def.ts — fund page PageDefinition (reference example)
  customize.test.ts — 13 unit tests for schema/migration/ops (keep green)
```

## Layout schema v2

```ts
interface Section   { id: string; columns: 1|2|3|4; widgets: WidgetState[] }  // one widget per column slot
interface PageLayout{ version: 2; sections: Section[]; presetId?: string }
```

- v1 flat layouts (`{ widgets: [...] }`) auto-upgrade via run-length grouping by span.
- Unknown/stale widget ids are dropped; widgets missing from storage are appended in an
  overflow section (layouts survive app updates).
- Storage keys: `eclipse_<page>_layout_v2`; `loadLayout` falls back to the legacy
  non-`_v2` key so existing users migrate transparently.

## Adding a customizable page (checklist)

1. Widget meta map: `Record<WidgetId, WidgetMeta>` (`label`, `desc?`, `defaultSpan`, `defaultHeight?`).
2. Presets as **section templates**: `sections: [[2, 'widget-a', 'widget-b'], [1, 'widget-c']]`
   (tuple = `[columnCount, ...widgetIds]`). Unlisted widgets append in a trailing overflow section.
3. `PageDefinition`: `{ pageId, storageKey: 'eclipse_<page>_layout_v2', widgets, presets }`.
4. In the screen: `const c = useCustomize(MY_PAGE);`
5. Render:
   - **Canvas**: map `layout.sections` → wrap each in `<SectionShell editing={customizing}
     columns={s.columns} onColumns={(cols) => c.setColumns(s.id, cols)} onDelete={...}>`,
     inside it a grid with the page's section grid class (1→`lg:grid-cols-1`, 2→`md:grid-cols-2`,
     3→`md:grid-cols-2 lg:grid-cols-3`, 4→`md:grid-cols-2 lg:grid-cols-4` — keep static strings
     so Tailwind's scanner sees them). Each widget wrapper is a drop target calling `c.place(...)`.
   - **Panel (Navigator)**: same tree rendered as rows — section header + StructurePicker +
     draggable widget chips (eye + height steppers). Copy the markup from `my-portfolio.tsx`.
6. Tests: extend `customize.test.ts` if you add kernel ops.

## Interactions (must match everywhere)

- **Columns**: hover a section → `StructurePicker` → pick 1/2/3/4 columns; widgets reflow,
  overflow spills into a new section.
- **Move**: drag a card (or Navigator chip) onto a section (appends) or onto another card
  (inserts before it). Cross-section moves prune emptied sections.
- **Height**: per-widget `height` in 40px steps (+/− in Navigator, edge handles on canvas).
- **Visibility**: eye toggle anywhere; fully-hidden sections don't render.
- **Presets** apply a full section template in one click.

## Conventions & anti-patterns

- Widget ids are stable strings — renaming requires a storage migration in `layout.ts`.
- Keep widget render logic in the screen; the kernel owns only layout state.
- Never hand-roll a second column/structure picker or panel style; reuse `SectionShell` +
  `StructurePicker` + the Navigator row look so every page feels identical.
- Never store layouts in an untyped shape — always `PageLayout` via the kernel.