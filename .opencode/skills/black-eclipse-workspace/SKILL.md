---
name: black-eclipse-workspace
description: Black-Eclipse reusable customizable-workspace system — the drag-and-drop / click-to-place widget grid used by the Command Center dashboard and portfolio fund workspaces. Use when building or editing any customizable page, adding widgets, wiring a new page to the workspace engine, or extending the widget library / config panel. Always reuse the shared CustomizableWorkspace component and WidgetDefinition contract instead of hand-rolling a layout engine.
---

# Black-Eclipse Workspace — Reusable Customizable Widget Grid

The workspace engine lets any page become a user-customizable grid of widgets
(sections → columns → cards) with drag-and-drop, click-to-place, left/right
swap, duplicate, hide, per-instance config, and a searchable widget library.
It is the SAME engine behind the Command Center dashboard and the portfolio
fund workspaces. Do NOT build a second layout engine.

## Architecture

```
Page (e.g. FundWorkspace, DashboardScreen)
   │  supplies: storageKey, defaultLayout, widgets[], widgetIcon, renderWidget
   ▼
CustomizableWorkspace  (src/components/workspace/customizable-workspace.tsx)
   │  composes: useWorkspace + WorkspaceCanvas + WidgetLibrary + WidgetConfigPanel
   ▼
Workspace kernel  (src/lib/workspace/)
   ├─ types.ts        WidgetPlacement { id, widgetId, height, config, hidden }
   ├─ ops.ts          pure Immer layout ops (move/add/remove/resize/duplicate/…)
   ├─ persistence.ts  localStorage, corrupt-data-never-overwritten guard
   ├─ use-workspace.ts Zustand store per storageKey
   └─ workspace-canvas.tsx  dnd-kit drag/drop + click-to-place chrome
```

## The reusable pieces

- **`CustomizableWorkspace`** (`src/components/workspace/customizable-workspace.tsx`)
  — the one-stop composite. A page only needs to pass:
  - `storageKey` (unique localStorage key per page/instance)
  - `defaultLayout` (`WorkspaceLayout`)
  - `widgets` (`WidgetDefinition[]`)
  - `widgetIcon` (name → lucide component)
  - `renderWidget` (widgetId, placement → ReactNode) — the source of truth for
    rendering; thread page data (fund, market data, etc.) through here.
  - optional `editBarExtra` (extra chrome in the edit bar)
- **`WidgetDefinition`** (`src/lib/workspace/widget-def.ts`) — the plug-and-play
  widget contract: `{ id, category, label, desc, icon, sizes, defaultConfig?,
  configFields?, dataDeps?, refreshPolicy?, lazy?, render? }`. `render` is
  optional — the host's `renderWidget` is authoritative.
- **`WidgetLibrary`** (`src/components/workspace/widget-library.tsx`) — searchable,
  categorized palette with Favorites + Recently Used. Takes `widgets` + `widgetIcon`
  as props (no hard-coded registry).
- **`WidgetConfigPanel`** (`src/components/workspace/widget-config.tsx`) — renders
  `configFields` and saves to `placement.config`. Takes a `getDefinition` resolver.

## How to add a customizable page

1. Define your widgets as `WidgetDefinition[]` (see `portfolio/widgets.tsx` for a
   real example). Give each a stable `id`, a `category`, `label`, `desc`, `icon`
   name, and `sizes`.
2. Provide a `widgetIcon(name)` resolver mapping your icon names to lucide icons.
3. Provide a `renderWidget(widgetId, placement)` that renders your widget content
   (threading your page's data/props).
4. Build a `defaultLayout` (see `defaultFundLayout()` in `portfolio/widgets.tsx`).
5. Render `<CustomizableWorkspace storageKey=… defaultLayout=… widgets=… widgetIcon=… renderWidget=… />`.

## Interaction model (both supported)

- **Drag-and-drop**: click-hold-drag a card, release to place.
- **Click-to-place**: single-click a card to pick it up (floating ghost + live
  drop-line follow the cursor), then single-click a target spot to place it.
  Clicking the same card again drops it back; Esc/right-click cancels.
- **Left/right swap buttons** on each card move it to the adjacent column
  (creating one if needed).
- **Duplicate / hide / remove / fit-height** buttons on each card in edit mode.

## Design rules

- Use the frosted-glass classes (`.glass-card`, `-strong`, `-subtle`) per the
  `black-eclipse-ui` skill. The edit bar uses `.ws-glass`.
- Widgets are pure: they consume data via props and report null/empty where data
  is missing — never fabricate financial data.
- Persistence is automatic via the kernel; corrupt stored data is never
  overwritten (falls back to defaults, leaves the payload untouched).

## Gotchas

- The edit-chrome container on each card stops `pointerdown` AND `click`
  propagation so its buttons don't trigger card grab/place. The grip handle has
  its own dnd-kit listeners so it still starts a drag.
- `WidgetDefinition.render` is optional; prefer the host's `renderWidget` so page
  data can be threaded in. Only set `render` for self-contained widgets.
