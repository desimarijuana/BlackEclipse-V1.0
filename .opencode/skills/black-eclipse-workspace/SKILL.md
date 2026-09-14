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
  - optional **rail zone**: `railClassName`, `railHeader`, `railCollapsed`,
    `onToggleRail`. When any section is `zone:'rail'` the canvas lays the main
    zone and the rail side-by-side under ONE DndContext — see "Zones" below.
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
  the workspace's **rail zone** — not a separate page/panel. Its widgets live in
  `src/lib/dashboard/market-rail-widgets.tsx` (`MARKET_RAIL_WIDGETS`,
  `marketPanelIcon`) and are merged into the single `DASHBOARD_WIDGETS` catalog.
  The default rail sections come from `buildRailSections()` in
  `src/lib/dashboard/registry.tsx`; `dashboard-screen.tsx` appends them to the
  template layout and passes one `CustomizableWorkspace` with `railClassName` +
  `railHeader` + `railCollapsed`/`onToggleRail`.

## Zones (centre + rail)

A workspace layout is a flat list of sections, each tagged with an optional
`zone: 'main' | 'rail'` (undefined = `main`). The canvas renders all `main`
sections in the primary column and all `rail` sections in a narrow column beside
it — **both under one `DndContext`**, so cards drag freely between the centre and
the rail, and **one Customize button drives everything**. Never build a second
customization surface / second workspace for a side column.

- Sections created via strips inherit the anchor section's zone
  (`createSectionAt` / `moveWidgetToNewSectionAt` / `addWidgetToNewSectionAt`).
- `normalizeLayout` preserves the zone; `pruneLayout`/`cloneLayout` carry it.
- `useWorkspace` runs a one-time migration: if the `defaultLayout` has rail
  sections but the stored layout has none, it appends the default rail sections
  (and persists) so existing dashboards gain the rail without losing their
  centre arrangement — no storage-prefix bump needed.
- The rail is only active when `railClassName`/`railHeader` are passed AND the
  layout actually contains rail sections; single-zone pages (fund workspaces)
  are unaffected.

## How to add a customizable page

1. Define your widgets as `WidgetDefinition[]` (see `portfolio/widgets.tsx` for a
   real example). Give each a stable `id`, a `category`, `label`, `desc`, `icon`
   name, and `sizes`. Add `dataDeps` for any live data the widget needs.
2. Provide a `widgetIcon(name)` resolver mapping your icon names to lucide icons.
3. Provide a `renderWidget(widgetId, placement)` that renders your widget content
   (threading your page's data/props).
4. Build a `defaultLayout` (see `defaultFundLayout()` in `portfolio/widgets.tsx`).
   For a centre + rail page, append rail sections (see `buildRailSections()`).
5. Render `<CustomizableWorkspace storageKey=… defaultLayout=… widgets=… widgetIcon=… renderWidget=… statusBar=… />`.

## Toolbar (always visible)

`CustomizableWorkspace` renders a toolbar with **Compact** (row height 60→40px),
**Refresh** (force-refresh all topics), and **Customize** (enter edit mode).

## Widget catalog (Command Center)

The dashboard registry (`src/lib/dashboard/registry.tsx`) ships a 36-widget
catalog across categories: Markets, Research, Portfolio, Trading, Tools,
Geopolitics. Real data widgets live in `src/lib/dashboard/widgets.tsx` and
consume DataHub topics (indices, forex, crypto, commodities, movers, news,
economic calendar, quotes). Widgets needing external/broker integrations
(Quick Trade, Open Positions, Live TV, Geopolitics, etc.) render a clear
`UNAVAILABLE` state — never fabricate data. Add a widget by registering a
`WidgetDefinition` in the registry and (optionally) a renderer in `widgets.tsx`.

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

## Paper broker (trading widgets)

The paper broker (`src/lib/dashboard/paper-broker.ts`) is a deterministic simulated
broker persisted to localStorage — positions, orders, margin, P&L, fills. It is
the default broker until real broker adapters (Alpaca/Zerodha/KTrade/Questrade/IG)
are wired with credentials. Paper fills are REAL simulated executions, clearly
labeled — never fabricated market data.

Trading widgets (`src/lib/dashboard/trading-widgets.tsx`) consume the
`broker:account` DataHub topic:
- **Quick Trade** — place market orders (BUY/SELL).
- **Open Positions** — live positions with unrealized P&L.
- **Working Orders** — pending orders, click × to cancel.
- **Margin Usage** — available/used margin, usage %.
- **Today P&L** — aggregate P&L.

The broker adapter interface (`src/lib/broker/types.ts`) will unify real brokers
behind one interface; the paper broker implements the same shape.

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
