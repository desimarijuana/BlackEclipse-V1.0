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
- **`MarketSidePanel`** (`src/components/workspace/market-side-panel.tsx`) — reusable
  collapsible right-hand market overview column: Fear & Greed gauge, market breadth,
  top gainers/losers, global snapshot (VIX/US 10Y/DXY/Gold/Oil/BTC), and market-hours
  status dots (NYSE/LSE/Tokyo/Shanghai/NSE). Data flows through the DataHub
  (`panel:*` topics). Mount beside a `CustomizableWorkspace` in a flex row.

## How to add a customizable page

1. Define your widgets as `WidgetDefinition[]` (see `portfolio/widgets.tsx` for a
   real example). Give each a stable `id`, a `category`, `label`, `desc`, `icon`
   name, and `sizes`. Add `dataDeps` for any live data the widget needs.
2. Provide a `widgetIcon(name)` resolver mapping your icon names to lucide icons.
3. Provide a `renderWidget(widgetId, placement)` that renders your widget content
   (threading your page's data/props).
4. Build a `defaultLayout` (see `defaultFundLayout()` in `portfolio/widgets.tsx`).
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
