---
name: black-eclipse-workspace
description: Black-Eclipse reusable customizable-workspace system — the drag-and-drop / click-to-place widget grid used by the Command Center dashboard and portfolio fund workspaces. Use when building or editing any customizable page, adding widgets, wiring a new page to the workspace engine, or extending the widget library / config panel. Always reuse the shared CustomizableWorkspace component and WidgetDefinition contract instead of hand-rolling a layout engine.
---

# Black-Eclipse Workspace — Reusable Customizable Widget Grid

The workspace engine lets any page become a user-customizable grid of widgets
(sections → columns → cards) with drag-and-drop, click-to-place, drag-from-library,
section add/delete, left/right swap, duplicate, hide, per-instance config, and a
searchable widget library. It is the SAME engine behind the Command Center
dashboard and the portfolio fund workspaces. Do NOT build a second layout engine.

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
   ├─ ops.ts          pure Immer layout ops (move/add/remove/resize/duplicate/
   │                  removeSection/addWidgetToNewSectionAt/…)
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
  - optional `toolbar` (`'default'` labelled buttons · `'compact'` icon-only ·
    `'none'`) and `hideFloatingAdd`.
  - optional `defaultCompact` — start with dense rows.
  - optional **side zones**: `zones={{ left?, right? }}`, each a
    `{ className?, header?, collapsed?, onToggle? }` config. When a section is
    tagged `zone:'left' | 'right'`, the canvas lays that zone beside the `main`
    centre under ONE DndContext — see "Zones" below. The legacy `railClassName` /
    `railHeader` / `railCollapsed` / `onToggleRail` props are **deprecated
    aliases for `zones.right`** and still work.
- **`WidgetDefinition`** (`src/lib/workspace/widget-def.ts`) — the plug-and-play
  widget contract: `{ id, category, label, desc, icon, sizes, defaultConfig?,
  configFields?, dataDeps?, refreshPolicy?, lazy?, render? }`. `render` is
  optional — the host's `renderWidget` is authoritative.
- **`WidgetLibrary`** (`src/components/workspace/widget-library.tsx`) — searchable,
  categorized palette with Favorites + Recently Used. Takes `widgets` + `widgetIcon`
  as props (no hard-coded registry). Rows support TWO add modes (both reported via
  `onStartAddDrag(id, label, mode)`):
  - `mode: 'hold'` — press a row and drag past a 5px threshold, release to place.
  - `mode: 'click'` — a plain click starts **project mode**: a ghost follows the
    cursor with the live drop-line; a **single click on the canvas places** it
    (a double-click also confirms; right-click / Esc cancels).
  While an add is in flight the palette goes `pointer-events-none` so
  `elementFromPoint` reaches the canvas underneath.
- **`WidgetConfigPanel`** (`src/components/workspace/widget-config.tsx`) — renders
  `configFields` and saves to `placement.config`. Takes a `getDefinition` resolver.
- **`DataHub`** (`src/lib/workspace/data-hub.ts`) — client-side pub/sub data layer.
  Widgets declare `dataDeps` (topic ids); the hub batches fetches per topic, caches
  with a TTL, and fans results to subscribers. Hidden widgets unsubscribe so they
  don't burn rate limits. A failed topic only marks that topic `UNAVAILABLE`.
  - `registerTopic(jsonTopic(id, url, { ttl, interval }))` at module load.
  - `useTopic<T>(id)` hook subscribes a component; `useRefreshAll()` returns a
    force-refresh fn (F5 fan-out).
- **`StatusBar`** (`src/components/workspace/status-bar.tsx`) — reusable bottom
  status strip: version, feed indicators (EQ/FX/CM/FI/CR), session uptime, layout
  status, feeds connected, memory usage, API latency, pending-orders badge, bell.
  Mount via `CustomizableWorkspace`'s `statusBar` prop.
- **`MarketSidePanel`** was REMOVED. The Command Center's Market column is now
  the workspace's **right zone** — not a separate page/panel. Its widgets live in
  `src/lib/dashboard/market-rail-widgets.tsx` (`MARKET_RAIL_WIDGETS`,
  `marketPanelIcon`) and are merged into the single `DASHBOARD_WIDGETS` catalog.
  The default right-zone sections come from `buildRailSections()` and the left
  column from `buildLeftSections()` (asset-class aware via `ASSET_LEFT`) in
  `src/lib/dashboard/registry.tsx`; `dashboard-screen.tsx` appends them to the
  template layout and passes one `CustomizableWorkspace` with `zones={{ left, right }}`.

## Zones (centre + left/right)

A workspace layout is a flat list of sections, each tagged with an optional
`zone: 'left' | 'main' | 'right'` (undefined = `main`). The canvas renders all
`left` sections in one narrow column, all `main` sections in the centre, and all
`right` sections in a second narrow column — **all under one `DndContext`**, so
cards drag freely between them, and **one Customize button drives everything**.
Never build a second customization surface / second workspace for a side column.

- Legacy storage: the two-zone era used `zone:'rail'` for the right column.
  `normalizeLayout` maps `rail → right` on read, so no storage-prefix bump.
- Sections created via strips inherit the anchor section's zone
  (`createSectionAt` / `moveWidgetToNewSectionAt` / `addWidgetToNewSectionAt`).
- `normalizeLayout` preserves the zone and `hiddenZones`;
  `pruneLayout`/`cloneLayout` carry them.
- `useWorkspace` runs a one-time migration per side zone: if the `defaultLayout`
  has `left`/`right` sections but the stored layout has none, it appends the
  defaults (and persists) so existing dashboards gain the side columns without
  losing their centre arrangement.
- **Remove vs collapse.** `onToggle` only *collapses* a zone to a slim handle
  (ephemeral). To fully **remove** a panel use the edit bar's **Left panel /
  Right panel** toggles → `workspace.ops.setZoneHidden(zone, hidden)`, which
  records the zone in `layout.hiddenZones` and *keeps its sections*, so re-showing
  restores the exact widgets. Prefer this for "remove a section" requests.
- A zone renders only when its sections exist, the host passed its config, and it
  is not in `hiddenZones`; single-zone pages (fund workspaces) are unaffected.

## How to add a customizable page

1. Define your widgets as `WidgetDefinition[]` (see `portfolio/widgets.tsx` for a
   real example). Give each a stable `id`, a `category`, `label`, `desc`, `icon`
   name, and `sizes`. Add `dataDeps` for any live data the widget needs.
2. Provide a `widgetIcon(name)` resolver mapping your icon names to lucide icons.
3. Provide a `renderWidget(widgetId, placement)` that renders your widget content
   (threading your page's data/props).
4. Build a `defaultLayout` (see `defaultFundLayout()` in `portfolio/widgets.tsx`).
   For a centre + side-columns page, append `left`/`right` sections (see
   `buildLeftSections()` / `buildRailSections()`).
5. Render `<CustomizableWorkspace storageKey=… defaultLayout=… widgets=… widgetIcon=… renderWidget=… zones={{ left, right }} statusBar=… />`.

## Toolbar (always visible)

`CustomizableWorkspace` renders a toolbar with **Compact** (row height 60→40px),
**Refresh** (force-refresh all topics), and **Customize** (enter edit mode).

## Widget catalog (Command Center)

The dashboard registry (`src/lib/dashboard/registry.tsx`) ships the full widget
catalog across categories: Markets, Research, Portfolio, Trading, Tools,
Geopolitics, Intelligence. Real data widgets live in `src/lib/dashboard/widgets.tsx`
and consume DataHub topics (indices, forex, crypto, commodities, movers, news,
economic calendar, quotes). Widgets needing external/broker integrations
(Quick Trade, Open Positions, Live TV, Geopolitics, etc.) render a clear
`UNAVAILABLE` state — never fabricate data. Add a widget by registering a
`WidgetDefinition` in the registry and (optionally) a renderer in `widgets.tsx`.

The **Investor Eye** widget (`src/lib/dashboard/investor-eye-widget.tsx`) is a
thin view over the same Investor Eye DataHub state topics the full screen uses
(`investor-eye:state:<hours>`), with `range` + `lens` config fields. Its spatial
companion, the **Investor Eye Map** widget
(`src/lib/dashboard/investor-eye-map-widget.tsx`), embeds the real
`components/investor-eye/WorldMap` (2D map or lazy 3D globe) over the same state
topics + `buildAllLayers()`, and writes selection to the shared
`useInvestorEyeStore` — no second fetch path and no fabricated data. Its map
chunk is `next/dynamic`-split so dashboards without it never load
ECharts/`echarts-gl`. Register new widgets at the END of `DASHBOARD_WIDGETS` —
the persona templates (`src/lib/dashboard/templates.ts`) address widgets by array
index, so inserting mid-list silently repoints every template.

## Chart widgets

ECharts line charts live in `src/lib/dashboard/chart-widgets.tsx`:
- **Asset Chart** — price line with EMA 20/50 + RSI 14 (from `/api/price-history`).
- **Economic Data Chart** — economic series line (from `/api/economics`).
- **Macro Snapshot** — central-bank rates + key prints (from `/api/economics/snapshot`).
- **Fund Performance Chart** — fund NAV vs SPY (stubbed until a portfolio API exists).

Reuse the `useEChart` binding + `baseChartOption` from
`src/components/screens/portfolio/use-echart.ts` for consistent frosted styling.
Indicators (EMA/RSI) are computed deterministically client-side — never fabricated.

## Intelligence widgets

Deterministic market intelligence lives in `src/lib/dashboard/intelligence.ts`
(pure functions) + `src/lib/dashboard/intelligence-widgets.tsx` (renderers):
- **Market Regime** — Risk On/Off, Trending Bull/Bear, Range, High Volatility, with measurable factors (breadth, momentum, volatility).
- **What Changed?** — session-over-session index changes (deterministic, no LLM).
- **Opportunity Scanner** — momentum/mean-reversion setups with WHY (checks + risks), never framed as prediction.
- **Market Drivers** — what's moving markets, ranked by absolute change.

All consume the same DataHub topics (`market:indices:US`, `market:overview`) as the other widgets — no extra fetches.

## Trading widgets (NOT IMPLEMENTED)

There is **no broker integration** — no paper broker, no broker adapter, no
`trading-widgets.tsx`. Every `trading`-category widget (Quick Trade, Open
Positions, Working Orders, Margin Usage, Today P&L) renders the shared
`UnavailableStub` in `src/lib/dashboard/registry.tsx`. Do NOT fabricate fills or
positions; wiring a real broker adapter is a prerequisite.

## Interaction model (all supported)

- **Hold-and-place** (drag): click-hold a card and drag, release to place.
- **Click-to-project** (cards & adds): a single click *projects* the card/widget
  (floating ghost + live drop-line follow the cursor). A **single click on a
  target places immediately** (the classic two-click flow); a **double-click
  also confirms** and **right-click / Esc cancels**. Clicking the same card
  again cancels the grab.
- **Add from the library** uses the same two modes:
  - *hold* — press a palette row, drag out, release to place;
  - *click* — click a palette row to project, then double-click to place.
  Dropping onto an inter-section **“New section” strip automatically creates a
  new section** holding that widget (`ops.addWidgetToNewSectionAt`).
- **Sections**: inter-section strips create sections; the **trash button in each
  section’s edit controls deletes that section** (`ops.removeSection`, confirm
  guarded; at least one section always remains).
- **Left/right swap buttons** on each card move it to the adjacent column
  (creating one if needed).
- **Duplicate / hide / remove / fit-height** buttons on each card in edit mode.

## Design rules

- Use the frosted-glass classes per the `black-eclipse-ui` skill. The workspace
  **edit bar uses `.glass-card`**; the **widget library + config drawers use
  `.glass-drawer`** (a lower-opacity / higher-blur tier that reads as real frost
  over the dark page). Do NOT use the near-opaque `-strong` tier for these.
- Widgets are pure: they consume data via props and report null/empty where data
  is missing — never fabricate financial data.
- Persistence is automatic via the kernel; corrupt stored data is never
  overwritten (falls back to defaults, leaves the payload untouched).

## Gotchas

- The edit-chrome container on each card stops `pointerdown` AND `click`
  propagation so its buttons don't trigger card grab/place. The grip handle has
  its own dnd-kit listeners so it still starts a drag.
- Add is NOT a dnd-kit drag: it reuses the canvas’s real-pointer projection
  (`computeTarget(..., '__add__')`) and renders its floating ghost through a
  portal. In `'click'` mode `pointerup` does NOT commit — a real single click on
  the canvas (the workspace `onClick`), a double-click, or a drop on an empty
  column does. The host (`CustomizableWorkspace`) owns `addingWidgetId` /
  `addingMode` and passes a stable `onAddingEnd` (useCallback); it also ignores
  palette-backdrop closes for ~450ms after an add so the trailing click of a
  double-click doesn’t shut the panel.
- The library’s full-screen backdrop intercepts pointer events; close the drawer
  (or run an add-project, which sets `pointer-events-none`) before interacting
  with cards underneath.
- `WidgetDefinition.render` is optional; prefer the host's `renderWidget` so page
  data can be threaded in. Only set `render` for self-contained widgets.
- **Canvas/chart widgets must handle a zero-size mount.** A card can render a
  frame before flex layout resolves its height, and some libraries crash on a
  0×0 container (ECharts' geo map throws
  `Cannot read properties of null (reading '0')`). Gate the chart init on a
  non-zero box and let a ResizeObserver start it once the box is real — see
  `hasDrawableBox()` in `src/lib/investor-eye/map-echarts.ts` and the init effect
  in `components/investor-eye/world-map.tsx`.
