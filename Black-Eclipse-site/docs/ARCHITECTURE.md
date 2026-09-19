---
title: Architecture
status: Current
last-verified: 2026-09-18
---

# Architecture

**Who this is for:** a developer about to make a structural change, or anyone
trying to understand how the pieces fit.

This is the *map*. For "why", read [`DECISIONS.md`](./DECISIONS.md). For
"where is the file", read [`NAVIGATION.md`](./NAVIGATION.md). For the data path,
read [`DATA-FLOW.md`](./DATA-FLOW.md).

> The authoritative, more detailed engineering brain lives in
> [`../skills/ARCHITECT.md`](../skills/ARCHITECT.md). Where the two overlap, that
> file is the deeper reference and this one is the readable summary.

## Layer 0 — The shell

`src/app/page.tsx` renders `<StockChat />` inside an `ErrorBoundary`. That is the
whole routing story for the app: **one page**.

`src/components/screens/stock-chat.tsx` is the SPA shell and owns:

- the `activeTab` state machine,
- keep-alive tabs (mount on first visit, then `display:none`),
- conversation persistence in `localStorage` (`chats_guest`),
- deep-link boot (`/?symbol=AAPL` opens the chart),
- the command-palette destination bus, and the `be:navigate` custom event,
- the full-viewport **Aurora** glow driven by combined sentiment.

Screen chunks are loaded with `next/dynamic` + `ssr: false` so first paint only
compiles the chat shell. This is a deliberate memory/perf decision — do not
convert these to static imports.

### Keyboard ownership

Function-key navigation shares the persisted sidebar configuration; it does not
introduce a second router. Untouched legacy defaults migrate to assigned keys,
while customized assignments and disabled sections are preserved. F11 remains
unassigned by default because browsers use it for fullscreen.

`src/hooks/use-page-shortcuts.ts` registers page actions against visible DOM
roots, with matching and guards in `src/lib/keyboard.ts`. Keep-alive screens
must never receive actions while hidden. Focused nested scopes take precedence;
editable controls, composition, repeated presses, consumed events and blocking
dialogs suppress page commands. Custom overlays must declare dialog semantics
or `data-keyboard-overlay="true"` to participate in this guard. Chart drawing
commands additionally require ownership by the focused chart.

The root-mounted `src/components/layout/keyboard-shortcuts.tsx` exposes Ctrl/Cmd+/
help using the sidebar settings and registered action metadata. Page groups
reflect mounted screens, so visiting a screen registers its contextual commands.
Handlers reuse existing UI actions; creation shortcuts open forms rather than
submit financial mutations. Browser/OS-reserved function keys cannot be
guaranteed by a web app and remain user-reassignable in Sidebar settings.

Three other keyboard affordances build on the same dispatcher rather than adding
listeners:

- **Executable palette commands** (`src/lib/search/commands.ts`, rendered by
  `global-search.tsx`). `Ctrl+K` runs real actions — quick alert, watchlist add,
  chart, fund open/export, Journal, Settings sections — reusing existing helpers
  such as `createQuickAlert`. Side effects live on an `ExecutableCommand.run`
  field, never on registry actions, because the resolver calls `action.run()` on
  every keystroke.
- **List navigation** (`src/hooks/use-list-navigation.ts`). Roving selection for
  news, screener tables, alerts, journal trades and the Investor Eye feed. It
  tracks selection by stable id, not index, so sorting or a refresh cannot move
  the selection. Screens opt in with their existing root scope.
- **Sub-tabs and history.** `Alt+1..9`/`Alt+0` select sub-tabs (Journal,
  Economics). Because there is no router, `src/components/screens/navigation-history.ts`
  keeps a capped in-memory stack of visited tabs that `Alt+←` walks back through.

## Layer 1 — Screens & components

```
src/components/
  screens/        full-page views + their data/hook modules
  layout/         sidebar, top-bar, price-ribbon, global-search, agentation
  chat/           chat-specific pieces
  ui/             reusable primitives (button, card, dialog, tab-bar, …)
  chart/          the ECharts/TradingView chart widget
  journal/        trading journal UI
  market-workspace/  the multi-panel market grid UI
  workspace/      the customizable widget-grid UI
```

Conventions: `'use client'` at the top of client files, **named exports**, and
the `cn()` helper from `src/lib/utils.ts`. UI primitives come from
`src/components/ui/`; do not hand-roll a new one.

## Layer 2 — Client data layer

Two mechanisms:

1. **DataHub** (`src/lib/workspace/data-hub.ts`) — a singleton client-side
   pub/sub. Widgets declare `dataDeps` (topic ids); the hub batches one fetch per
   topic, caches with a TTL, auto-refreshes on an interval, and fans the result
   out. Topics are registered with `registerTopic(jsonTopic(...))` at module load
   and consumed with `useTopic<T>(id)` / `useRefreshAll()`.
   - Hidden widgets unsubscribe, which stops the refresh timer — this is the
     rate-limit protection.
   - A failed topic becomes `UNAVAILABLE`; it never takes down the dashboard.
   - Provenance is explicit: `LIVE | CACHED | HISTORICAL | DEMO | ESTIMATED |
     UNAVAILABLE`.
2. **Zustand stores** for UI state (sidebar config, dashboard layouts, search,
   market-workspace, aurora palette) — persisted to `localStorage`, not the DB.
3. **Portfolio engine** (`src/hooks/use-portfolio-engine.ts`) — pure FIFO/LIFO
   cost-basis and stats logic, consumed by both the portfolio screens and the
   dashboard portfolio widgets. There is **no broker integration yet**: every
   `trading`-category widget (Quick Trade, Open Positions, Working Orders, Margin
   Usage, Today P&L) renders the shared `UNAVAILABLE` stub in
   `src/lib/dashboard/registry.tsx`. Do not fabricate fills — wire a real broker
   adapter first.

## Layer 3 — API routes

`src/app/api/**/route.ts`. Route handlers are thin and server-only. Mutating
routes are protected by `src/lib/api-guard.ts`:

- `checkMutationAllowed` / `guardMutation` — a three-tier policy: same-origin
  browser requests always pass; a correct `CRON_SECRET` (Bearer or `x-api-key`)
  passes; otherwise the request must come from localhost.
- `rateLimit` / `guardExpensiveMutation` — in-memory fixed-window per-IP limiter
  for expensive endpoints.
- `checkOutboundUrl` / `filterSafeUrls` — SSRF allowlist for user-configurable
  feed URLs. **RSS feeds only.** Arbitrary operator APIs go through the stricter
  connector path in `src/lib/connectors/security.ts` (DNS validation + pinning,
  redirect blocking, size cap) — see "The Universal Data Connector Layer".

Key route groups: `stocks`, `quote`, `price-history`, `markets` (+`global`),
`indices`, `forex`, `commodities`, `heatmap`, `news` (+`status`, `alert`),
`economics` (+`snapshot`, `calendar`), `earnings`, `search` (+`global`, `index`), `agent`
(+`chat`, `research`, `activity`), `journal/*` (largest group), `alerts/*`,
`scraper` (+`import`), `refresh`, `settings`, `cron` (+`run`, `refresh-news`),
`data-sources` (+`test`), `datasets`, `data/[capability]`, `providers`,
`asset-details`, `symbols`, `commodities`.

## Layer 4 — JDDS (the data vault)

**JDDS = "Joint Data Distribution System".** One SQLite file (`jdds.db`) accessed
through Prisma with the `better-sqlite3` adapter. `src/lib/db.ts` owns the client
and exports `prisma` plus `yieldToEventLoop()` (critical: better-sqlite3 is
synchronous, so bulk writers must yield or they freeze the server).

The schema (`prisma/schema.prisma`) is organized in domains:

| Domain | Models |
|---|---|
| Market universe | `Market`, `Asset`, `Price`, `IndexQuote` |
| News | `NewsItem`, `SourceHealth` |
| Macro | `MacroSeries` |
| Scheduling & config | `CronJob`, `SystemConfig` |
| Agentic research memory | `ResearchReport`, `AgentRun`, `ResearchFinding` |
| Alerts | `PriceAlert`, `PriceAlertEvent`, `Candles` |
| Data connectors | `DataConnector`, `CustomDataset`, `CustomDatasetField`, `CustomDatasetRecord`, `ConnectorMapping` |
| Investor Eye | `Country`, `GeopoliticalEvent`, `EventEntity`, `Relationship`, `SourceRun` (`GeopoliticalEvent.category` distinguishes hazard sub-types via a nullable column — additive, no migration needed) |
| Trading journal | `JournalProfile`, `TradingAccount`, `Strategy`, `StrategyRule`, `Setup`, `Tag`, `JournalDay`, `DailyReview`, `DailyEmotion`, `Trade`, `TradeExecution`, `TradeScreenshot`, `TradeAnnotation`, `TradeTag`, `MarketContext`, `JournalEntry`, `Review` |

Two design notes that matter:

- **Dedup by constraint.** `Asset` is unique on `[marketId, symbol]`; `Price` is
  keyed by `assetId`; `NewsItem` has a `dedupKey`. Imports are idempotent upserts,
  not inserts.
- **Auth-ready, not auth-ful.** The journal carries an optional owner concept so
  a `User` relation can be added later without a rewrite. There are no accounts
  today — the app is a guest app.

### Journal demo data is real rows, clearly labelled

The journal is DB-backed, unlike the localStorage portfolio demo, so a fresh
install would otherwise open on eight empty tabs. `src/lib/journal/demo.ts` seeds
~90 days of deterministic sample trades at boot (`src/instrumentation.ts`) and
from `scripts/seed-journal.ts`.

Three invariants make shipping demo rows into a user's database safe:

1. **`Trade.source`** (`'manual' | 'demo'`) marks provenance. The UI shows a
   banner whenever demo rows are present, and "Remove demo data" deletes only
   `source: 'demo'` rows — anything the user added is untouched.
2. **One-time marker.** A `SystemConfig` key (`journal_demo_seeded_v1`) records
   that seeding ran, so clearing the demo data does not bring it back on the next
   boot. The seeder also refuses to run when ANY trade already exists.
3. **Deterministic + internally coherent.** A seeded PRNG means identical data on
   every install. Positions are sized as `riskTarget / stopDistance` against the
   profile's own `accountSize × riskPerTrade`, so risk-per-trade varies gently
   (CV ≈ 0.1) instead of by orders of magnitude — which is what makes the risk
   analytics (risk consistency, the 1% rule, expectancy in R) meaningful rather
   than noise.

### Indices are tickers, not `Asset` rows

Indices are addressed by their **Yahoo ticker** (`^GSPC`, `^NSEI`, `^FTSE`,
`000001.SS`), not by the bare TradingView ids (`SPX`, `DJI`, `NIFTY`) — Yahoo has
no `SPX` instrument, so a bare alias silently produces an empty series. They also
are not in `Asset`; only `IndexQuote` holds their latest level. `src/lib/indices.ts`
is therefore the single source of truth: `resolveIndex()` maps any alias to the
canonical ticker (case- and caret-insensitive), and `searchIndices()` powers
autocomplete. Aliases that collide with real listed instruments (`DAX`, `STI`,
`SSE`) are `searchOnly` — they surface in search but never resolve implicitly, so
charting `DAX` still means the ETF.

Most indices come from the Yahoo chart endpoint. Yahoo **delisted PSX**, so the
Pakistan benchmarks are `provider: 'psx'` and served by
`src/lib/scraper/fetchers/psx-index.ts` from the exchange's own endpoints
(`dps.psx.com.pk/historical` for daily OHLC, `/timeseries/eod/<sym>` for the
latest quote).

### `Price.volume` is not one unit — turnover is the comparable metric

`Price.volume` means different things depending on how the market was ingested:

| Source | What `volume` holds |
|---|---|
| Binance (`connectors/providers/crypto.ts`) | quote-currency **notional** (`quoteVolume`, already in USD) |
| TradingView / yfinance (equities) | **share count** |

Summing share counts across differently-priced stocks is dimensionally
meaningless, and multiplying a notional by price double-counts. So the volume
tooling (`src/lib/heatmap.ts`) normalises both into **turnover** — traded value
in the market's own currency:

- notional markets (crypto): `turnover = volume` (no price multiply)
- share markets (everything else): `turnover = volume × price`

`isNotionalVolume(market)` / `turnoverFor(volume, price, market)` are the single
source of truth; `summarizeVolume()` builds the whole-market profile (total,
mean/median, top contributors, concentration HHI, contribution bands). Bands are
each instrument's **share of market turnover**, not an absolute amount, so they
stay meaningful across USD/PKR/IDR. `GET /api/heatmap?volume=1` serves this as
`HeatmapPayload.volume`, scanned over EVERY priced instrument (not just the
tiles). Feed markets (FOREX/COMMODITIES) have no real traded volume and omit it.

### Portfolio analytics are date-aligned, not position-aligned

`src/lib/portfolio/matrix.ts` owns the fund workspace's correlation and risk
decomposition. Two invariants make its numbers trustworthy:

1. **Date alignment.** Two markets have different trading calendars (NYSE vs PSX
   vs crypto's 7-day week), so `closes[i]` is NOT the same day for two symbols.
   Every statistic is computed on the **intersection of dates** for the pair it
   concerns; comparing position *i* to position *i* would silently correlate
   different calendar days, which is the classic way a correlation matrix lies.
   Pairs with fewer than `MIN_OBSERVATIONS` (20) shared returns render as an
   explicit `·`, never a plausible-looking `0.00`.

2. **Returns are currency-neutral.** r = P_t/P_{t−1} − 1 is a ratio, so native and
   USD-converted series of the same asset give identical returns. Correlations
   are therefore computed on native-currency closes and are correct for a mixed
   USD/PKR/INR book with no FX step. (A currency's own move is a separate
   exposure and is not captured — the widget says so.)

Risk is decomposed with the Euler method: `σ_p = √(wᵀΣw)`, `MCTRᵢ = (Σw)ᵢ/σ_p`,
`CTRᵢ = wᵢ·MCTRᵢ`, and each holding's **share of total risk** is `CTRᵢ/σ_p` (sums
to 100%). `Σ` is assembled as `corr_ij · σ_i · σ_j` so it agrees with what the
correlation widget displays. Pairwise-complete correlation is not guaranteed
positive-semidefinite, so variance is clamped at 0 and negative contributions are
dropped rather than surfaced as negative risk.

Mixed currency: `useLiveQuotes` keeps the **real** `marketId` and currency that
`/api/quote` returns (it used to re-derive a USD/PKR binary from a hardcoded
symbol allowlist, mislabelling an Indian holding as USD). `computePortfolioStats`
converts any currency via a live `fxToUsd`, falling back to a documented
approximation table and flagging the holding `fxMissing` so the UI can call that
USD value an estimate.

## Background workers

All in-process, all started from `src/instrumentation.ts`:

| Worker | Cadence | Source |
|---|---|---|
| Price refresh | configurable, default 15 min | `src/lib/scraper/scheduler.ts` |
| Universe sync | daily | `src/lib/scraper/scheduler.ts` |
| News ingest | default 5 min | `src/lib/news/ingest.ts` |
| Boot warm-up | once, prod-only by default | `src/lib/scraper/scheduler.ts` |
| Alert monitor | polling loop | `src/lib/alerts/alertMonitor.ts` |
| Dataset refresh | per-dataset, min 5 min | `src/lib/connectors/refresh-scheduler.ts` |
| Investor Eye ingest | default 10 min | `src/lib/investor-eye/scheduler.ts` |

They coordinate through mutex flags (`isRunning`, `syncBusy`, `warmUpBusy`) so
two heavy SQLite write storms never run at once. This is not incidental — running
them concurrently is what used to freeze the API.

## The two workspace systems (read this twice)

| | Widget workspace | Market workspace |
|---|---|---|
| Engine | `src/lib/workspace/` | `src/lib/market-workspace/` |
| UI | `src/components/workspace/` | `src/components/market-workspace/` |
| Powers | Command Center dashboard | Chart Workspace tab |
| Unit | widget card in a column | chart/market panel |
| Shape | track board: sections → columns (tracks) → widgets, packed masonry, + `left`/`right` zones | panels with presets/ops |
| Persistence | `localStorage` via `use-workspace` | `localStorage` via `use-market-workspace` |

### Widget workspace zones (three-column shape)

A layout is a flat list of sections, each tagged with an optional
`zone: 'left' | 'main' | 'right'` (undefined = `main`). The canvas renders all
`left` sections in a narrow column, all `main` sections in the centre, and all
`right` sections in a second narrow column — **all under one `DndContext`** and
**one Customize surface**, so a card drags freely between the three. Each
section's columns are its vertical tracks; within a multi-track section the
compose-time masonry packer balances cards (see the track-board grammar above),
and cards size to content with a per-widget floor.

Key invariants:

- **No second engine / no second customization surface** for a side column. The
  Command Center's Watchlist (left) and Market (right) are ordinary workspace
  sections, not separate panels.
- **Legacy `rail` = `right`.** Stored layouts from the two-zone era are mapped
  `rail → right` by `normalizeLayout` on read (no storage-prefix bump).
- **Side-zone migration.** `useWorkspace` seeds missing default `left`/`right`
  sections once (persisted), so existing dashboards gain the side columns without
  losing their centre arrangement.
- **Remove ≠ delete.** `setZoneHidden(zone, hidden)` records the zone in
  `layout.hiddenZones`; its sections stay in the tree so re-showing restores the
  exact widgets. Exposed as the **Left panel / Right panel** toggles in Customize.
- Per-zone presentation (`className`, `header`, `collapsed`, `onToggle`) is passed
  via `CustomizableWorkspace`'s `zones` prop; the old `rail*` props are deprecated
  aliases for `zones.right`.
- **Layout tabs are drag-to-reorder.** `TabBar` takes an `onReorder(fromId, toId)`
  prop (HTML5 drag on each tab); `market-tabs.tsx` maps it through
  `useMarketViews.reorder`. Double-click still renames and widget
  rearrangement (drag/click-to-place) is unchanged.
- **Side panels are drag-resizable.** A vertical handle between each side zone and
  the centre sets that zone's width live (clamped 180–520px) and commits on
  release through `ops.setZoneWidth`, persisted in `WorkspaceLayout.zoneWidths`
  (presentation-only — it never touches the section tree). Resizing works in both
  normal and edit mode; `main` is not resizable.

Both workspace systems are real and both are supported. The **retired** thing is
`src/lib/customize/` — an earlier kernel that is documented as superseded and
must not receive new features. See ADR-005 and ADR-006.

### Dashboard layout grammar (personas + track board)

The *default* arrangement of the Command Center is composed by the pure,
unit-tested engine in `src/lib/dashboard/layout.ts` (registry stays about
widgets, this stays about arrangement):

1. **Templates** (`src/lib/dashboard/templates.ts`) are authored as **widget-id
   specs**, never registry indices — inserting a widget in the registry can no
   longer silently repoint a template. A template is **centre-only**. Each
   persona authors one or more bands (`full(...)` or `board(widgets, tracks)`).
2. **`buildMarketViewLayout`** frames the template with the two thin side zones
   (left = Watchlist; right = the market's asset-class `mp-*` stat tiles) and
   composes everything through `composeBoard`.
3. **`composeBoard`** is the single enforcement point for the invariants:
   - **global first-wins dedupe** across every zone (a widget renders once, never
     in both the centre and a rail),
   - **build-time 4-track cap**, clamped to the card count so a band never
     creates an empty track,
   - **content sizing** in two modes — a FRAME (`defaultHeight`, for charts /
     maps / live video / scrollable tables & feeds) whose body stretches to fill
     the card, or a GROW floor (`minHeight`, for compact tiles). See
     `WIDGET_FRAME_HEIGHT` / `WIDGET_MIN_HEIGHT`; a `BoardCell` of `{ id, h }`
     can override a widget's frame for deliberate asymmetry,
   - **masonry balance** — `rebalanceColumns` (in `src/lib/workspace/pack.ts`)
     distributes each section's cards into the shortest track by estimated
     height,
   - unknown ids dropped.

The side rails are each a **single stacked section**, not one section per tile.
The old per-widget sections wrapped every tile in its own section gap + padding,
which is what made the dashboard look full of gaps.

**Gap-free by construction.** In the retired row-band grammar a section was a
rigid full-width row of content-height columns (`items-start`), so any short
widget left dead space beside a tall sibling, and the side rails (pinned 300px /
4×190px) left ~490px blank under the Watchlist. The track board instead treats a
section's **columns as vertical tracks** and packs cards into the shortest one, so
the next card flows underneath a short one. Cards size to content with a floor
(no oversized pinned bands to clip against), and the centre defaults to
**`CENTRE_TRACKS` (3)** balanced tracks — enough room that KPI tiles never
truncate. The 4-track engine capability remains for user drag/drop.

**Packing is compose-time, not edit-time.** `rebalanceColumns` runs when building
defaults, templates and imports — never inside the store's `commit`. Re-packing on
every edit would silently reshuffle cards the user just arranged (masonry has no
stable fixed point for equal-height cards), so a drag commits exactly where it was
dropped and the packer only shapes starting layouts.

**Twelve personas ship, each with a genuinely different SHAPE (band structure)
and widget set — not index shuffles:** `tape-reader` (full chart → wide tape →
two-up → TV), `desk` (dense 4-track: chart + heatmap + TV top row), `allocator`
(portfolio: performance hero → holdings → risk), `rates-desk` (economic chart +
rates + calendar), `chain-desk` (crypto hero row → chart → venue grid),
`fx-desk` (FX pairs hero → chart → drivers/macro), `screener` (heatmap +
screener full → momentum grid), `map-room` (map hero → event feed → conflict
layers), `newsroom` (news + calendar lead, charts second), `risk-desk` (regime +
risk above the chart), `trader-pro` (dual charts + candle + tape), `research`
(news categories + agent work + charts).

A band cell may be a plain widget id or `{ id, h, min, frame }`, letting a
persona pin a specific frame height where the default would read badly.

**A `defaultHeight` card gets a definite `height`, not `min-height`.** Frame
widgets (charts, maps, live video, scrollable tables) put `absolute inset-0` /
`h-full` children inside a `flex-1` body; those only resolve against a definite
height. Rendering a frame as `min-height` left the ECharts canvas at **0px** —
the "blank charts/maps/heatmaps" bug. `cardStyle` therefore emits `height` for
`defaultHeight`, and `minHeight` remains a grow floor for compact tiles. Widgets
added from the library carry their intrinsic sizing (`addWidget(..., sizing)`).

**Storage v8 is a deliberate RESET.** v7 replaced the row-band grammar with the
track board; v8 fixes the persona rename. Because the nine personas gained new
ids but stored layouts keep the OLD id in `templateId`, `getDashboardTemplate`
returned `undefined` and the centre rendered EMPTY (only the side rails).
`templates.ts` now ships `LEGACY_TEMPLATE_IDS` + `resolveTemplateId` (old ids
resolve to their renamed persona; unknown/empty ids fall back to the first
persona), `use-workspace` self-heals a fully blank stored layout, and the
storage prefix reseeds everyone (`be_dashboards_index_v8` /
`be_ws_dashboard_v8_`; older keys are absent from `LEGACY_INDEX_KEYS`; fund
layouts are `be_ws_fund_*_v3`). **When renaming a persona, always add its old id
to `LEGACY_TEMPLATE_IDS`.**

`WorkspaceLayout.version` is `2`; `normalizeLayout` upgrades any stored payload
to v2 on read (mapping legacy `rail → right`, preserving `minHeight` /
`defaultHeight` and `zoneWidths`).

### Command Center fullscreen

`DashboardScreen` has an in-app fullscreen mode (`Shift+F`; header button; `Esc`
exits). It renders the **real app `<TopBar activeTab="dashboard" />`** — the live
price ribbon and the global ⌘K search — so fullscreen keeps the market chrome
rather than inventing its own bar. There is no dedicated full-width bar; a
floating **Exit** button sits bottom-right. The overlay is **portaled to
`<body>`**: the app shell is wrapped in a glass-card whose `backdrop-filter`
establishes a containing block, so a plain `position: fixed` overlay would be
trapped inside it and the global nav would stay on top — the same reason the
Chart Workspace portals its full-page overlay. Body scroll is locked while open;
the workspace owns the height and scrolls.

Because the overlay sits ABOVE the app shell, the shell's Aurora (`z-0`) is
covered — so fullscreen mounts its own **`<AuroraGlow>`**
(`src/components/layout/aurora-glow.tsx`). `AuroraGlow` is the single reusable
glow: it owns the market+news sentiment subscription (`market:indices:US` +
`aurora:news-score` topics) and the user palette, and renders the masked top
band. The shell and fullscreen both use it, so the sentiment model stays in one
place (`src/lib/aurora-sentiment.ts`). Any future full-viewport overlay must do
the same — the shell's glow does not reach above it.

### ChatDock (the Command Center assistant composer)

`src/components/chat/chat-dock.tsx` is the floating, **bottom-centre** assistant
bar mounted on the Command Center (collapsed = composer only; the transcript
expands above it once there is a conversation). It is a **view over the existing
chat stack**, not a second one: it renders `ChatHistory`, calls
`getAgentProvider()` for ordinary questions and `/api/agent/research` for
research intents (the same heuristic the ChatBot tab uses). Invariants:

- **It owns its own conversation.** Persisted to `localStorage`
  (`be_chat_dock_v1`), separate from the ChatBot tab's shell-owned `chats_guest`
  state, so opening it never mutates or races the full chat screen.
- **A body portal must gate itself on the HOST TAB's display, never on viewport
  intersection.** The Command Center is a keep-alive tab hidden with
  `display:none`, and a `createPortal` to `<body>` is NOT hidden by an ancestor's
  `display:none`. The dock walks up to the keep-alive panel
  (`[data-keepalive-panel]`, set by `stock-chat.tsx`) and reads its
  `display`/`visibility`, re-reading via a `MutationObserver` when the tab's
  `class` toggles. Do **not** use an `IntersectionObserver` here: the dashboard
  scrolls, a zero-size sentinel scrolls out of view, the observer reports
  "hidden", and the always-on composer disappears mid-scroll.
- **Always-on overlays are NOT `data-keyboard-overlay`.** That marker declares a
  *blocking dialog* and would disable every page shortcut while the dock is
  mounted. The dock is therefore only `data-nodrag`; the focused composer input
  already suppresses shortcuts via the editable-element guard.
- **Never fabricate a model name.** The provider pill renders
  `getAgentProvider().label` — the real configured provider.

It renders at `z-[90]` (above the fullscreen overlay's `z-[80]`) and takes a
`className` so fullscreen can lift it clear of the Exit button. Two independent
collapse controls: the **transcript** expand/collapse (and Escape, captured so it
does not also exit fullscreen), and a true **minimize** that shrinks the whole
dock to a restore pill — persisted (`be_chat_dock_minimized_v1`) so the user's
small-vs-big choice survives reload. The minimized pill is **draggable**: it
defaults to the viewport bottom-right corner and, once moved, anchors by
`top`/`left` with its position persisted (`be_chat_dock_pill_pos_v1`) and
re-clamped on resize (`clampPill`). Click (no drag) restores the dock; a press
that passes a 4px threshold becomes a drag. The composer overlays the board; it
does not reserve layout space.

### Shipped default dashboard board

`src/lib/dashboard/default-board.ts` exports `DEFAULT_BOARD_JSON`. Paste a
Command Center **Export** payload's `layout` there and every NEW user (and every
Reset) starts from that curated arrangement instead of a generic persona.
`getDefaultBoard()` validates it through `normalizeLayout` against the live
registry, so an unknown/retired widget id or a malformed paste degrades to the
persona template — a bad paste can never ship an empty or broken first-run
board. `DEFAULT_BOARD_JSON = null` means "ship the persona templates unchanged".
A layout explicitly created from a persona preset still honours that preset.

### Compact mode was removed

The widget workspace no longer has a compact/row-height mode. It forced every
card to a fixed 40px height, crushing widget content. Cards now size to their
widget (auto, filling the column) or to a per-placement pinned height.

## The command center (⌘K)

`src/components/layout/global-search.tsx` (palette) + `src/components/layout/top-bar.tsx`
(header trigger) sit on top of `src/lib/search/`. The flow is two pure steps:

1. **Grammar** (`search/grammar.ts`) — `parseQuery(raw)` splits the raw query into a
   *scope* (a leading prefix: `>` commands, `#` symbols, `@` indicators, `/` pages,
   `~` your data, `?` help), *free text*, and *field operators* (`kind:`, `class:`,
   `market:`, `symbol:`/`asset:`). It is framework-free and unit-tested
   (`grammar.test.ts`) so the vocabulary can grow without touching the UI.
2. **Resolver** (`search/resolver.ts`) — classifies intent, scores the static
   registry + FlexSearch universe, and applies the parsed scope/filters
   (`scopeKinds`, `matchesFilters`) plus a recency multiplier. It returns
   `ResolvedSearch` including the `parsed` query and a `showHelp` flag.

Invariants: search is **fully offline and deterministic** — no LLM on the query
path (only the explicit "Ask AI" escalation row). Navigation is a *destination
bus*: the palette dispatches a `Destination`, the shell subscribes to
`pendingDestination`, so no component reaches into the router. The command-center
vocabulary (scopes/operators) is a user-facing contract — extending it means
editing `grammar.ts` and its tests together.

**Intelligence & actions.** Beyond the resolver:
- `resolver.ts` `expandTerms` (a curated synonym/acronym table) turns "gold",
  "us jobs data", "fed rate" into the right symbol at a score discount, so an
  explicit match still wins. Ranking is personalized by entity *visit* history
  (`recencyScore` opt; the palette feeds it `visitRecencyScore` from the store).
- `calc.ts` powers an inline offline calculator + indicative currency conversion;
  `commands.ts` detects parameterized verbs (`alert`, `watch`, `chart`) and
  offers argument autocomplete. Both are pure and unit-tested.
- Parameterized commands **run real side effects**: `alert SYMBOL` creates a
  ±3% `CHANGE_PCT` watch via `lib/alerts/quick-alert.ts` (`POST /api/alerts`)
  and opens the Alerts tab; `watch SYMBOL` calls `addToWatchlist`
  (`lib/dashboard/watchlist-store.ts`) and opens the dashboard; `chart SYMBOL`
  opens the chart. Registry actions declare `requiresArg`, so they are excluded
  from ordinary action matching and can never render as a bare command that
  navigates without acting.

**Cross-tab pivots.** `resolveQuery` returns `related` rows for a resolved
instrument. These are honest about what each destination can do: the news pivot
passes `params.symbol`, which `MarketNews` consumes via its `symbol` prop (it
seeds the server-side `ticker:` query operator — the news API has no other
per-symbol filter); the screener pivot passes `symbol` + `focus:'chart'`, which
pre-fills `MarketOverviewScreen`'s `initialSymbol` → `stockSearch` (the screener
has no single-symbol query — it is a paginated universe partition, so a ticker
narrows the search box rather than defining a new filter dimension).

**Result UX.** The resolver returns `total` (untruncated match count, for
"showing N of M"), a `suggestion` "did you mean" on a zero-hit query (static
registry only), and `related` cross-tab pivots for a resolved instrument. The
palette groups results by entity kind with per-group counts and collapsible
headers, pins entities (persisted in `localStorage`, replayed from a serialized
destination), and copies symbols. Pins, visits, and collapse state live in the
command store — the resolver stays pure.

**Sub-page list + scrolling.** The palette's bottom **Pages** group lists the
**sub-pages only** (the top-level tabs live in the sidebar and still resolve
through search). It is **generated from `getPageEntries().filter(p => p.child)`**
— not hand-listed — so registering a sub-page adds a row automatically. Labels
are qualified by parent tab (`Journal · Analytics`, `Screener · Crypto`) because
several share a name. The group is collapsible (shared `collapsedGroups` key
`'nav'`) and is part of the same flat keyboard list. Navigation keys: ↑/↓ (wrap),
PageUp/PageDown (jump `PAGE_SIZE`), Home/End, Enter to run. A bottom gradient
fades in only while the list can still scroll (`canScrollDown`, tracked via
scroll + ResizeObserver), so overflow is visible without a permanent shadow.

**Sub-route routing (sub-pages).** A `Destination.subroute` is how the palette
targets an internal view (`economics.calendar`, `journal.analytics`,
`discovery.crypto`, `alerts.create`, `settings.aurora`). The shell's `apply()`
publishes it to `useCommandStore.requestSubroute(tab, subroute, focus)` — a
*channel*, not a single slot, so two screens never steal each other's request.
The owning screen consumes it with `useSubroute(tab, handler)`; both live in
`src/hooks/use-subroute.ts`. Two invariants:
- **Subscribe, don't read once.** Screens are keep-alive (`display:none`), so a
  tab revisit does not remount — a mount-time prop would silently never fire
  again. `useSubroute` subscribes and clears the request once applied.
- **`settings` is a modal, not a tab.** `tab: 'settings'` is routed to the
  Settings dialog (keyed by section), because no tab screen exists for it —
  switching to it would render nothing.

**Accessibility.** The input is an ARIA combobox driving a `role="listbox"`
result list with `aria-activedescendant`; a polite live region announces result
counts. Rows are memoized so selection changes don't re-render the whole list.

**Header price ribbon.** `src/components/layout/price-ribbon.tsx` is the live,
**user-customizable** ticker strip mounted in `top-bar.tsx` beside the search
trigger. The configured symbols live in `src/lib/ribbon/store.ts` (localStorage,
same storage-event pattern as the guest watchlist) and are **routed by family**:

- catalog instruments (commodities `GC=F`, FX `EURUSD=X`; registered in
  `src/lib/market-catalog.ts`, which is also the single source of truth for
  `/api/commodities` and `/api/forex`) come from the shared `market:commodities`
  / `market:forex` topics;
- everything else (indices, stocks, crypto) goes to a dynamic
  `ribbon:quote:<sorted symbols>` topic over `/api/quote?symbols=…`.

A symbol the upstream cannot price is omitted rather than shown as a fake zero.
Clicking a quote dispatches a `{ tab: 'chart', params: { symbol } }` destination
on the command bus; the trailing gear opens a portaled customization popover
(add via the same database autocomplete the pin inputs use, remove, reset).
Presentation: **no background** (bare text, reads as market chrome), and the
marquee (`.price-ribbon` / `.price-ribbon-track` in `globals.css`) renders two
copies and translates `from -50% to 0` for continuous **left→right** motion,
pausing on hover and disabled under `prefers-reduced-motion`.

## The Universal Data Connector Layer

`src/lib/connectors/` is a capability-addressed layer that lets the operator
bring their own REST API into BlackEclipse. It is **additive**: the scraper
chain still runs first, and route-level demo fallbacks are untouched.

```
Scraper chain (existing)  →  Connector tier (new)  →  route-level demo (where it already exists)
```

**Provider ≠ capability.** Consumers ask for `PRICE`; the resolver
(`resolver.ts`) picks a connector. Precedence is deterministic: built-ins
(`kind: 'builtin'`, currently Binance crypto) outrank operator connectors, and
ties break by id. There is **no automatic cross-provider fallback** — if the
primary connector fails, the result is `UNAVAILABLE`. The resolver never
fabricates demo data.

| File | Owns |
|---|---|
| `types.ts` | `DataConnector`, `Capability`, `ConnectorResult`, `Provenance` |
| `registry.ts` | id → connector map (anchored on `globalThis`, like `db.ts`) |
| `resolver.ts` | capability → ordered connectors (built-in first) |
| `runtime.ts` | `runCapability`, `syncCustomConnectors` |
| `custom-rest.ts` | declarative REST connector (GET, `{{param}}` substitution) |
| `draft.ts` | unsaved wizard-draft validation (shared by test + save) |
| `security.ts` | SSRF/IP classification, pinned DNS, capped body, safe GET |
| `secrets.ts` | AES-GCM credential encryption + key resolution |
| `mapping.ts` | `recordPath`, field coercion, `recordKey` dedup |
| `refresh.ts` | multi-value pull expansion + `PullSummary` |
| `refresh-scheduler.ts` | the `dataset_refresh` cron |
| `health.ts` | application-level health state (no Prisma enum) |
| `store.ts` | JDDS persistence (connectors, datasets, records) |
| `catalog.ts` | the browsable provider catalog (grouped, honest status) |
| `builtins.ts` | built-in connector registration (avoids a barrel cycle) |
| `providers/crypto.ts` | Phase-2 proof: the migrated crypto fetcher |

**Security.** Every outbound connector request goes through `safeGet`:
https-only, WHATWG-canonicalized, DNS resolved and validated **then pinned at
connect** (rebinding-safe; TLS/SNI preserved), `redirect: manual`, a streamed
5 MB cap, and a ≤10s timeout. Never `res.text()` on an untrusted response.

**Secrets.** Credentials are AES-256-GCM encrypted before they touch JDDS.
Single-node installs auto-generate `.connector-key` (gitignored); hosted
deployments must set `CONNECTOR_SECRET_KEY` because an instance-local file would
differ per instance. The browser sees only `hasSecret: boolean` after saving.

**Data integrity.** Custom records live in `CustomDataset` /
`CustomDatasetField` / `CustomDatasetRecord`. `(datasetId, recordKey)` is
unique, so re-imports upsert. `Asset`/`Price`/`Candles` are **never** written by
this layer — see ADR-010.

**Honest import accounting.** `ingestRecords` returns
`{ written, extracted, rejected, rejectedRequired, rejectedIdentity, deduped }`
so the UI reports "Imported 8 of 10 records · 2 rejected" instead of a blanket
success. Every extracted row is accounted for as written, deduped, or rejected.
A connector that needs parameters it did not receive returns **400**
(`invalid_config`/`missing_param`), not an opaque 502.

**Multi-value pulls.** A parameter value may be a comma-separated list
(`BTC,ETH,SOL`); `refresh.ts` expands it into **one request per value**, capped
at `MAX_VALUES_PER_PULL = 25` with the overflow count reported, never a silent
truncation, and requests spaced 250ms apart. `pullDataset` returns a
`PullSummary`; partial failure returns HTTP 207.

**Scheduled refresh.** `refresh-scheduler.ts` runs a `dataset_refresh` cron
(per-dataset due check, 90s boot grace). It reuses the scraper scheduler's
discipline: a mutex, sequential runs, and it **skips a tick while `syncBusy()`
holds the write path** — better-sqlite3 is synchronous. A failed dataset still
advances `lastRefreshAt` so it cannot retry every tick.

**Provider catalog.** `catalog.ts` is a map of what BlackEclipse can talk to,
grouped by purpose (AI, economics, market, crypto, custom). Economics entries are
**derived from `ECON_SOURCES`**, so the catalog cannot drift from the fetch
layer. Status is computed from the real environment (`builtin` / `connected` /
`not_configured` / `available`) and buttons never claim to have saved a key:
env-gated providers route to the screen that actually sets it.

**Providers live where they are configured.** Each settings section renders the
slice it owns — AI Agent (a preset picker), Market Data (market + crypto),
Integrations (economics), Data Sources (custom only) — rather than dumping all 72
into one screen. Long lists are collapsible and filterable.

**AI presets are one source of truth.** `src/lib/agent/presets.ts` declares every
OpenAI-compatible provider (base URL + default model). The AI Agent picker and
the catalog's AI entries are both derived from it, so adding a provider is one
edit. Every preset speaks the protocol `OpenAICompatibleProvider` already sends,
so "Use this" is a real choice. Local servers (Ollama, LM Studio) are marked
`keyless` and `setLLMConfig` permits them without an API key (`isLocalBaseUrl`).

**Key status has one list.** `CATALOG_ENV_VARS` is the single set of env vars the
UI reports; `/api/providers` and `/api/settings` both read it. Status is computed
from the real environment and buttons never claim to have saved a key.

**Server-side resolution.** DataHub stays client-side. It may return a
provenance envelope (`{ data, source }`) from a topic, and `capabilityTopic()`
wraps `GET /api/data/[capability]`; the route decides the connector and reports
provenance so widgets never invent a tag.

**New routes:** `GET/POST/PATCH/DELETE /api/data-sources`,
`POST /api/data-sources/test` (outbound → `guardExpensiveMutation`),
`GET/POST/PUT/DELETE /api/datasets`, `GET /api/data/[capability]`,
`GET /api/providers`.
**UI:** Settings → **Data Sources** (`data-sources-panel.tsx`) — the provider
catalog, the connector list, the add wizard (Configure → Authenticate → Test →
Map & define dataset), and a **Datasets** browser with **Pull**, per-dataset
parameter inputs, records with provenance, auto-refresh, and delete.

**Agent access.** Read-only `list_datasets` / `describe_dataset` /
`query_dataset` tools in `src/lib/agent/dataset-tools.ts`, spread into `TOOLS`;
every result states provenance.

**Deferred:** webhooks, POST/PUT bodies, pagination beyond value lists, OAuth,
`~` dataset search, AI-generated connectors, multi-user credentials.

## Fundamentals (the investor-analysis surface)

Fundamentals is the **filings-backed analysis** rendered inside the Market
Screener's stock detail popup — not a standalone sidebar tab. A stock row opens
the popup, whose **Fundamentals** tab shows the provider snapshot *and* the live
quote metrics on one page. It is a **separate provider tier** from the connector
layer: rather than picking one connector for a capability, it MERGES
complementary sources into one normalized document.

```
Provider → Normalization → JDDS → Fundamentals UI (Market Screener popup tab)
```

**The UI depends only on the Eclipse schema.** `src/lib/fundamentals/types.ts`
defines `FundamentalsSnapshot` (company, periods, metrics, growth, earnings,
ownership, insights, timeline). The panel in
`src/components/screens/fundamentals/` talks only to `/api/fundamentals` — it
never imports a Yahoo/SEC/FMP module.

| File | Owns |
|---|---|
| `fundamentals/types.ts` | The Eclipse schema (`FundamentalPeriod`, `FundamentalMetric`, `FundamentalsSnapshot`, `FundamentalsProvider`) |
| `fundamentals/normalize.ts` | Provider rows → one period shape; derives per-period ratios |
| `fundamentals/compute.ts` | Metric assembly, CAGRs, valuation, **data-driven insights/risks** |
| `fundamentals/format.ts` | Display formatting (percent metrics are FRACTIONS everywhere) |
| `fundamentals/providers/` | `sec-edgar`, `financialmodelingprep`, `yahoo` + precedence registry |
| `fundamentals/index.ts` | `getFundamentals(symbol, market)` — merge, cache, persist |
| `components/screens/fundamentals/panel.tsx` | The shared presentational sections (`FundamentalsBody`, `TickerHeader`, metric tiles, charts, states) |
| `components/screens/fundamentals/use-fundamentals.ts` | The client data hook |
| `scripts/yfinance_fundamentals.py` | The Yahoo statements/profile/estimates bridge |

**Precedence and merging.** `PROVIDER_ORDER` is
`sec-edgar → financialmodelingprep → yahoo`. The **first provider that returns
statement periods is the primary source**; quote, valuation multiples, earnings
and ownership are filled from whichever provider has them. A missing source is
never a fatal error — it fills what it can and marks the rest `UNAVAILABLE`.

- **SEC EDGAR** — preferred for US issuers, keyless. Ticker → CIK via the cached
  `company_tickers.json` map, then `companyfacts.json`. Only `10-K`/`20-F`/`40-F`
  annual values are read (latest filing wins per end date); **tag families are
  unioned** so a preferred tag that stops being reported (e.g. NVIDIA's revenue
  tag after FY2022) cannot blank a newer period, and sub-annual windows that
  share a fiscal end date are ignored. **EBITDA is derived** (operating income +
  D&A) and explicitly labelled, because the SEC does not tag it. Non-US markets
  skip this provider (`supports()` gates it).
- **Yahoo Finance** (`yfinance` bridge) — the universal fallback and the only
  source for non-US markets when no vendor key exists. Returns up to 5 fiscal
  years of real statements plus profile/ratios.
- **Financial Modeling Prep** — optional; enabled only when
  `FINANCIALMODELINGPREP_API_KEY` is set in Settings › API Keys or env. This is
  the reference secondary provider; Alpha Vantage can be added as another
  `FundamentalsProvider` with one file and one registry line.

**Caching / JDDS.** `getFundamentals` fronts the `FundamentalsCache` table
(`@@unique([symbol, market])`, `payload` = JSON snapshot) with an in-memory map.
A fresh entry (< 24h) is served directly; a stale one is served immediately while
a background refresh runs (stale-while-revalidate); beyond 7 days the request
blocks so the UI cannot present years-old data as current. Concurrent requests
for the same symbol share one in-flight fetch. Provider failures return the stale
copy rather than blanking the screen.

**Honesty rules.** Percent metrics are stored as fractions; a metric with no
inputs is `null` and renders `UNAVAILABLE` (never 0). Every metric carries
`value`, `period`, `yoy`, `source` (`sec-edgar` / `financialmodelingprep` /
`yahoo` / `derived`) and `updatedAt`. Insights are synthesized only from actual
statement inputs and list the metric keys they are grounded in. The valuation
history chart reconstructs multiples from the CURRENT price and each year's
reported EPS/revenue — it says so in the caption.

**Route:** `GET /api/fundamentals?symbol=…&market=…[&refresh=1]` (rate-limited).
**UI:** the Market Screener popup (`tradingview-chart.tsx`) **Fundamentals** tab,
which renders the shared `panel.tsx` sections — Overview (insight strip, metric
grid, revenue/EPS/FCF/margin/debt/valuation charts), Statements (period tabs +
statement table + growth), Valuation (multiples, earnings, ownership), Timeline
(filings + profile) — followed by the live price-history/performance/quote
sections of the old "All Metrics" tab. The market id is derived with
`countryToMarketId()` from `src/lib/markets.ts` because JDDS `Asset.country` is
inconsistent ("United States" vs "US").

## Investor Eye (the world-state surface)

`investor-eye` is a sidebar tab (keep-alive, `next/dynamic`-split like every
other screen) that renders a large interactive world and the intelligence
underneath it. The long-term model is:

```
world events → geopolitical conditions → economic transmission → markets
→ companies → securities → portfolios
```

**It is a new, additive tier — it does not replace or duplicate the scraper,
news, portfolio, or market systems.** The full audit, Phase 1/2 scope, and the
list of deliberate non-additions live in
[`investor-eye-architecture.md`](./investor-eye-architecture.md). ADR-011 records
the decision.

### Layers (the stack)

```
SOURCE (GDELT, USGS, NASA FIRMS, /api/indices, /api/economics + FRED CSV, JDDS Asset/Price)
  ↓ src/lib/investor-eye/sources/*     fetch via the shared connectors `safeGet`
RAW
  ↓ classify.ts / cluster.ts / dedup.ts / confidence.ts   (pure, unit-tested)
normalized + clustered events
  ↓ state.ts        assemble, cache (SWR), persist, provenance, SourceRun rows
JDDS (Country, GeopoliticalEvent, EventEntity, SourceRun) + in-memory cache
  ↓ /api/investor-eye/*  → DataHub topics (provenance envelope) → Zustand store
  ↓ layers.ts (pure builders) → MapLayer[] → <WorldMap> (ECharts)
```

Every source also has a `source-catalog.ts` governance entry (licence,
commercial-use, attribution, rate limit, freshness), and a test enforces that a
registered adapter cannot exist without one — see *Data governance* below.

| File | Owns |
|---|---|
| `types.ts` | `NormalizedEvent`, `EventSource`, `MapLayer`, `InvestorEyeState`, provenance |
| `countries.ts` | canonical country gazetteer (ISO codes, region, centroid, aliases, market link) |
| `admin-boundaries.ts` | point-in-polygon country lookup against the shipped Natural Earth GeoJSON (exact, cached) |
| `source-catalog.ts` | source governance: licence, commercial use, attribution, rate limit, freshness |
| `src/lib/provider-keys.ts` | the encrypted vault + registry for every operator credential (`/api/provider-keys`, settings → API Keys) |
| `classify.ts` | event type / severity / channels / commodities / sectors (pure) |
| `cluster.ts` | dedup clustering + internal data-quality confidence (pure) |
| `dedup.ts` | stable `dedupKey` for idempotent upserts |
| `geo.ts` | grid aggregation so dense events never render raw |
| `sources/` | `registry.ts` + `gdelt.ts` + `usgs.ts` + `news.ts` + `firms.ts` (`EventSource` adapters) |
| `state.ts` | `assembleState`, market observations, country summaries, `SourceRun` bookkeeping |
| `phase2.ts` | real economic metrics (FRED CSV), companies (JDDS `Asset`), price history |
| `analytics.ts` | risk decomposition, exposure, transmissions, analogues, NL `planQuery` |
| `graph.ts` | pure edge → nodes/links aggregation (per-kind caps, honest truncation) |
| `graph-data.ts` | derives + persists `Relationship` / `EventEntity` / `Country`; `queryEdges` |
| `cameo.ts` | CAMEO root code → event type, Goldstein → severity, **FIPS 10-4 → ISO2** |
| `relevance.ts` | investor-relevance score (0..1) + reasons; the feed's display threshold |
| `sources/news.ts` | turns existing `NewsItem` rows into events (no new feed/credentials) |
| `sources/firms.ts` | NASA FIRMS keyless fire CSV → grid-clustered detections (pixels, not fires) |
| `history.ts` | candle backfill + coverage, reusing the alerts yfinance path |
| `layers.ts` | pure `MapLayer` builders (events, markets, conflict, shipping, trade, energy, commodities, weather, fires, economy, companies, portfolio) |
| `map-echarts.ts` | the ONLY ECharts-aware module; layer → option + event bridge |
| `app-geo.ts` | loads/registers `public/geo/world.geo.json`; **draws the glowing globe texture** (gradient ocean, dark land, coastline bloom, city stipple) |
| `starfield.tsx` | the canvas starfield + nebula backdrop behind the map (deterministic, drawn once) |
| `cache.ts` / `scheduler.ts` | server SWR cache + persisted last-known; in-process ingestion cron |
| `store.ts` / `topics.ts` | Zustand view state; DataHub topics |

### Routes

`GET /api/investor-eye/state` · `/events` · `/events/:id` · `/countries/:id` ·
`/markets` · `/layers/:layer` (+ guarded `POST` rebuild) · `/economy` ·
`/companies` · `POST /portfolio` · `/risk` · `/analogues` · `/query` ·
`/graph` · `/history` (+ guarded `POST` backfill) · `/health`.

**Feed sources.** GDELT is read from its **bulk 15-minute Event export**
(`data.gdeltproject.org`) — fast, complete and not rate-limited — decoded with
Node's built-in `zlib` via `safeGet({ binary: true })`. The DOC API is only a
best-effort fallback: it was measured at >13s/request (the transport caps at
10s) and 429s on bursts. `sources/news.ts` additionally converts the
already-ingested `NewsItem` rows into events, so macro/market coverage costs no
extra feed. `sources/firms.ts` reads NASA FIRMS' keyless global archive CSV
(the Area API needs a `MAP_KEY`, which would break zero-config) and **aggregates
at ingestion**: ~25,600 single-pixel detections become ≤400 grid clusters, each
reporting its real detection count and summed FRP. GDELT's FIPS country codes
are mapped to ISO2 in `cameo.ts` — they conflict with ISO for several important
countries.

**Data governance.** `source-catalog.ts` holds one entry per upstream source
(licence, commercial-use, attribution, rate limit, freshness). It is deliberately
separate from the adapters: a licence question should not require constructing a
fetcher. A test asserts every registered adapter has an entry (and vice versa),
so a new source cannot ship without declaring its licence.
`/api/investor-eye/health` joins the catalogue onto the `SourceRun` accounting
and returns the required attribution lines; `SourceHealthPanel` renders them and
flags a runnable-but-undeclared source as a governance gap. "Public API" is never
treated as "free for commercial use" — each entry records what the provider
states, with a link.

**Domain layers match type OR channel.** `classify.ts` assigns each event one
type but many channels, so a `conflict` event can still carry the Shipping
channel. Filtering on type alone drew a fraction of the real signal (measured:
28 shipping-channel events vs 11 shipping-typed in a 24h window). `buildDomainLayer`
therefore accepts either, and `shipping`/`commodities` are separate layers.

**Exact country attribution.** `admin-boundaries.ts` does a real
point-in-polygon test against the *same* Natural Earth GeoJSON the map ships
(`public/geo/world.geo.json`), cached in-module. This is what makes a precise
coordinate resolvable at all: the gazetteer's nearest-*centroid* match put only
15% of live fire clusters in a country, point-in-polygon puts 97%. It also draws
on the boundary asset's own ISO2/name when the curated gazetteer has no entry
(the asset covers 173 features; the gazetteer fewer), so a proven hit is never
discarded.

**Optional work never blocks the map.** The candle-history backfill (~170s
across 30 markets) is fire-and-forget inside `assembleState`; awaiting it
blocked the first world-state response and made the map show "0 events".

**Operator credentials (`provider-keys.ts`).** Every key the app can consume is
declared once in `PROVIDER_KEYS` and surfaced in Settings → API Keys. Values are
AES-256-GCM encrypted in `SystemConfig` (the existing `connectors/secrets` path)
and never returned to the browser — the API reports only `stored`, `fromEnv` and
a masked hint. `applyStoredKeysToEnv()` copies vault keys into `process.env` at
boot, but a REAL env var always wins and is never overwritten; removal only
clears variables this process itself populated. That keeps the existing env-based
consumers working with no per-provider refactor while preserving deployment
authority. "Test" performs a real request and reports the real status code.

**Do not run `prisma generate` without restarting the dev server.** A client
generated before a schema change silently fails every write to that table;
`persistEvents` catches per-row errors by design, so the failure is invisible —
the map shows events that exist nowhere in the database.

**Shared, per-window cache.** The assembled-state cache and its in-flight
assembly guard live in `cache.ts` **anchored on `globalThis` and keyed by time
window**. Next evaluates each route handler in its own module instance, so a
module-level `let` gave every endpoint a separate cache — `/state`, `/risk`,
`/markets` and `/layers` each cold-ran the full source ingestion. One shared
cache/guard means a route fan-out triggers exactly one ingestion per window.
Do not "simplify" this back to module-level state.

**Agent access (the AI Analyst).** `src/lib/agent/investor-eye-tools.ts` adds
seven read-only tools (`get_world_events`, `get_country_intelligence`,
`get_world_markets`, `get_event_detail`, `get_relationships`,
`get_portfolio_exposure`, `get_risk_state`) spread into `TOOLS`, plus a `world`
research agent in `research.ts`. Every result states provenance and labels
`INFERRED` links, so the model cites structured data instead of inventing it.

### Honesty and failure rules (non-negotiable)

- A source that fails is `UNAVAILABLE` — never a fabricated zero. A healthy
  source observing zero events may honestly report `0`.
- Provenance is computed server-side; the client never invents a tag.
- `confidence` is internal data quality, never presented as certainty.
- Observed facts are separated from **potential exposure** and **inferred**
  relationships in every tooltip/panel (`OBSERVED | HISTORICAL | INFERRED |
  AI-INTERPRETED`).
- Partial failure does not break the page: the map renders from whatever the
  remaining sources produced, and the status chip reports each source's state.

## Earnings calendar (the Command Center)

`src/lib/earnings.ts` (server-only) + `GET /api/earnings` serve upcoming company
earnings to the `earnings-calendar` widget (topic `earnings:calendar`).
**Alpha Vantage `EARNINGS_CALENDAR?horizon=3month`** is the PRIMARY source, using
the `ALPHAVANTAGE_API_KEY` from the provider-key vault (read with
`resolveProviderKey` server-side; the key is **never** sent to the browser). A
zero-config install has no key, so the module falls back to **Nasdaq's public
earnings calendar** (`api.nasdaq.com/api/calendar/earnings`, no key) for the next
a bounded rolling window (last 7 → +35 days, weekends skipped, ~6 requests pooled
at a time) — so the widget works out of the box and labels the real source
(`Nasdaq` / `Alpha Vantage`). A present-but-rejected key also falls through to
Nasdaq, and the Alpha Vantage reason is preserved in the error text. Parsers
accept Alpha Vantage's header aliases (`estimate`/`estimatedEPS`) and session
spellings (`pre-market`/`post-market`, `time-pre-market`/`time-after-hours` →
BMO/AMC), plus parenthesised negative Nasdaq EPS (`($1.08)`). Caching is 6h with
a shared in-flight promise, and a stale cached result is served on failure. Only
when BOTH sources fail does it return `source: 'unavailable'` with a human
`reason`; rows are never fabricated. The widget renders a **month grid calendar**
(cells group rows by ISO day, with ticker chips; a selected-day detail list),
and clicking a company dispatches `{ tab: 'chart', params: { symbol } }` on the
command store.

## Live Intelligence (the Command Center media widget)

"Live Intelligence" is a Command Center dashboard widget that streams financial,
market, business and geopolitical broadcasters inside the widget grid. It is a
normal `WidgetDefinition` — it moves, resizes, configures and persists through
the shared workspace kernel like every other widget, and introduces no second
framework.

- **Channel registry** — `src/lib/dashboard/live-channels.ts` is the single
  source of truth. Every channel is a broadcaster's OWN official feed, and every
  channel id AND `@handle` was resolved from that network's page. The catalog is
  finance/market-scoped by design (entertainment, sport and lifestyle are
  excluded). `LiveCategory` groups the picker; `LiveStreamType` is
  `youtube | video | embed`. `lastKnownStatus` records only what a real playback
  test observed; the runtime resolver is authoritative.
- **Live resolver (server-side, cached)** — `src/lib/dashboard/live-resolver.ts`
  + `GET /api/live-streams` resolve each channel's CURRENT live video id and
  status, cached 3 minutes with a shared in-flight guard. **This exists because
  embedding `live_stream?channel=<id|handle>` is unreliable** — YouTube renders
  "This video is unavailable" inside the frame for many channels that *are* live,
  which is the original "UNAVAILABLE" bug. Two findings are load-bearing:
  1. `/embed/<resolved-video-id>` plays where `live_stream?channel=` does not.
  2. YouTube's `/channel/<UC>/live` page silently fails to expose a canonical
     live video for many channels whose `/@handle/live` resolves correctly — so
     resolution tries the handle first.
  Live ids rotate, so none are hardcoded. Status is classified from YouTube's own
  page metadata (`canonical watch?v=` + `"isLive":true` +
  `playableInEmbed`) — never fabricated.
- **Selection store** — `src/lib/dashboard/live-intelligence-store.ts` holds the
  app-level configuration (enabled channels, default channel, validated custom
  sources) in localStorage with the same storage-event pattern as the price
  ribbon and guest watchlist. The channel a *specific* card is watching is
  per-instance state, persisted by the widget under its own placement id — two
  cards can watch different feeds.
- **Player** — `src/lib/dashboard/live-intelligence-widget.tsx` embeds the
  provider's official player, preferring the resolved video id
  (`/embed/<id>`), falling back to `live_stream?channel=<handle>`, or an
  allowlisted embed. States: checking, live, offline (a *resolved* verdict — the
  provider has no live broadcast right now), stream error (retry / change
  channel / open at source), no channels configured, and paused/off-screen.
  Custom sources are validated by `parseCustomSource` + a host allowlist
  (`safeEmbedUrl`) so a user URL can never load an arbitrary origin.
  The status chip shows `LIVE` only when the resolver confirmed a live,
  embeddable stream, `OFFLINE` for a resolved no-broadcast, `CHECKING` otherwise.
- **Teardown** — the widget owns its own lifecycle (ADR-015). Because the shell
  keeps visited tabs MOUNTED and hidden with `display:none`, and
  `WidgetDefinition.lazy` is never read, an `IntersectionObserver` plus a
  `visibilitychange` listener unmount the iframe whenever the card is hidden,
  scrolled off, or the browser tab is backgrounded, and re-mount it on return.
- **No proxy.** The app never proxies, restreams, scrapes or rebroadcasts
  anything, never fabricates a stream URL, and makes no unverifiable claim about
  a stream's live state. The resolver reads a public page's metadata only.
- **Extension point** — `LiveIntelligenceEvent` is declared (and unused) as the
  shape a future transcript → event-detection pipeline would emit for Investor
  Eye. No producer exists yet, and none may fabricate its fields.

## Design system

All surfaces use the shared frosted-glass classes from
`src/app/globals.css`: `.glass-card`, `.glass-card-strong`,
`.glass-card-subtle`, `.glass-drawer`, `.glass-button`. Tab bars use `TabBar`
(`src/components/ui/tab-bar.tsx`), which has two container variants: `glass`
(default, heavy frosted strip) and `subtle` (the restrained `.tab-bar-subtle`
control-strip tier for dense/toolbar-adjacent rows, e.g. the Command Center
market tabs). There are hard rules about `backdrop-filter`, tint opacity, and
backdrop roots — see the
[`black-eclipse-ui` skill](../../.opencode/skills/black-eclipse-ui/SKILL.md).
Do not introduce raw `backdrop-blur-*` or flat fills for cards.

## Architectural rules (short list)

1. Reuse existing hooks/services/primitives before writing new ones.
2. Do not duplicate business logic (`use-screener-filters.ts`,
   `use-portfolio-engine.ts`, the agent layer).
3. Server-only logic stays in API routes — never in client components.
4. Do not change data shapes screens depend on without updating all consumers.
5. Do not add a dependency without justification; prefer the lighter option.
6. Keep files small — memory is the top constraint on this machine.
7. Simulated data is always labeled; missing data is `UNAVAILABLE`, never faked.

