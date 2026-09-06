# CUSTOMIZE.md — Customization System Patterns

> Read this before adding a customizable page, widget, or preset.
> The customization kernel lives in `src/lib/workspace/` — screens must **register, not hand-roll**.

---

## Core rule

Every customizable page uses the shared workspace kernel with the **section → column → widget model**.
Never write page-local layout state, localStorage code, or drag plumbing.

```
src/lib/workspace/
  types.ts        — WidgetPlacement { id, widgetId, height }, Column { id, weight: 1–6, widgets[] },
                    Section { id, columns[] (1–4) }, WorkspaceLayout { version: 1, sections },
                    DropTarget { sectionId, columnId|null, index }
  ops.ts          — Immer draft mutators (mutate the draft, return void): moveWidget,
                    moveWidgetToNewSection, addWidget, removeWidget, setColumnCount,
                    setColumnWeight (1–6), setWidgetHeight (min 140px), pruneLayout,
                    locate, normalizeLayout (corrupt-read guard)
  use-workspace.ts — Zustand store per storageKey (cached, survives mounts):
                    { layout, editMode, corrupt, dragging, selectedWidgetId, selected,
                      templates, ops: { addWidget, removeWidget, moveWidget,
                      moveWidgetToNewSection, setColumnCount, setColumnWeight,
                      setWidgetHeight, applyTemplate, resetToDefault, selectWidget, setDragging } }
  workspace-canvas.tsx — dnd-kit edit chrome: DndContext + PointerSensor (4px activation),
                    droppable columns / new-column zones / new-section strip, DragOverlay ghost,
                    card hover toolbars (drag grip, fit-height, remove), bottom height-resize
                    handles, column-width drag handles between columns
  workspace-drawer.tsx — add-widget palette + template picker + reset (confirm-guarded)
  templates.ts    — curated section templates (classic / trader / analyst / minimal)
  persistence.ts  — localStorage load/save/clear; corrupt payload never overwritten
  workspace.test.ts — 35 unit tests (ops wrapped in produce) — keep green
```

## Stack (ADR-006)

- **dnd-kit** (`@dnd-kit/core`) — drag & drop between columns/sections/containers
- **Zustand** — editor + layout + selection state, one store per workspace
- **Immer** — safe immutable layout updates (ops are draft mutators via `produce`)

Rules for new ops:
1. Signature: `(draft: Draft<WorkspaceLayout>, ...args) => void` in `ops.ts` — mutate, don't clone.
2. Wrap call sites in the store's `commit(recipe)` (persisting is automatic).
3. Add a unit test using the `runOp(op, layout, ...args)` helper in `workspace.test.ts`.

## Adding a customizable page (checklist)

1. Widget registry: `WorkspaceWidgetMeta[]` — `{ widgetId, label, desc }` per widget.
2. `defaultLayout()` for the page (see `widgets.ts` → `defaultFundLayout`).
3. `renderWidget(widgetId, placement)` returning the widget's React content.
4. In the screen: `const workspace = useWorkspace({ storageKey, defaultLayout, knownWidgetIds });`
   (`knownWidgetIds` = registry ids; unknown stored widgets are dropped on load).
5. Render `<WorkspaceCanvas workspace={workspace} widgets={REGISTRY} renderWidget={renderWidget} />`.
6. Edit-mode toggle button: `workspace.setEditMode(!workspace.editMode)`.

## Layout model

```
WorkspaceLayout { version: 1, sections: Section[] }
Section  { id, columns: Column[] }            // column count 1–4 via setColumnCount
Column   { id, weight: 1–6, widgets: WidgetPlacement[] }  // flex-grow width share
WidgetPlacement { id, widgetId, height: number|null }     // null = natural height
```

- Widgets stack vertically inside a column; drag reorders within/between columns,
  across sections, into new columns (dashed + zone), or into a new section (bottom strip).
- `pruneLayout` drops empty sections (keeps one, keeps empty columns as drop targets).
- Storage key convention: `be_ws_<page>_<id>_v2`.

## Interactions (must match everywhere)

- **Edit bar**: sticky "Customizing" row with Widgets/Templates drawer + Done button.
- **Move**: drag any card (edit mode) — ghost overlay follows, target columns highlight.
- **Height**: bottom-edge handle per card (commit on release); Scan icon resets to auto.
- **Column width**: drag handle between adjacent columns (edit mode); commits weight 1–6.
- **Column count**: −/+ stepper in the section edit row; displaced widgets relocate to last column.
- **Remove**: X on the card toolbar (edit mode only).
- **Add**: drawer palette; already-placed widgets are marked.
- **Templates / Reset**: confirm-guarded; replace the whole layout.

## Conventions & anti-patterns

- Widget ids are stable strings — renaming requires a persistence migration.
- Keep widget render logic in the screen; the kernel owns only layout state.
- Cards use the shared `CARD_CLASS` glass style; don't restyle per page.
- Never call `saveWorkspace`/`loadWorkspace` directly — go through the store ops.
- Never hand-roll a second drag system; extend `workspace-canvas.tsx`.

## Roadmap (incremental improvements planned)

- Undo/redo on the Zustand store (temporal middleware) for template/reset actions.
- Keyboard DnD (dnd-kit KeyboardSensor) and a11y announcements.
- Save/load custom layouts as user templates (export/import JSON).
- Per-widget visibility toggles in the drawer palette.
- Mobile-friendly column handles (currently desktop-only, `md:` gated).