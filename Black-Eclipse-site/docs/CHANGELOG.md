---
title: Change Log
status: Current
last-verified: 2026-09-15
---

# Change Log

**Who this is for:** anyone who wants to know *what changed, when, and whether
the docs were updated* — without reading git history.

This is a **required** artifact. Every task that changes the repository appends
an entry here, including changes that needed no doc update. It is the record that
proves the documentation obligation was considered rather than skipped.

## Rules

1. **Append, never rewrite.** Add new entries at the top of the log. Do not edit
   or delete past entries — a wrong entry gets a follow-up entry, not a rewrite.
2. **Newest first.** One `##` section per date, entries as bullets beneath it.
3. **Group by date**, not by commit. Multiple changes on the same day share a
   date section.
4. **Link the docs.** Each entry ends with either the doc files it updated or
   `no doc change — <reason>`.
5. **Keep it terse.** One bullet per change: what changed and why it mattered.
   The diff holds the detail; this holds the *narrative*.

## Entry format

```markdown
## YYYY-MM-DD

- **<Area>** — <what changed and why>.
  docs updated: `docs/<file>.md`
- **<Area>** — <what changed and why>.
  no doc change — internal refactor, contracts unchanged.
```

`<Area>` is a short label: `Docs`, `Scraper`, `Workspace`, `Journal`, `Agent`,
`UI`, `DB`, `Alerts`, `API`, `Search`, `Economics`, `News`, `Charts`, `Build`.

---

## 2026-09-18

- **Command Center / Earnings** — Fixed "no data" when no key is configured and
  added the keyless fallback. Alpha Vantage stays primary, but a zero-config
  install has no `ALPHAVANTAGE_API_KEY`, so `earnings.ts` now falls back to
  **Nasdaq's public earnings calendar** (no key) for the next 5 weekdays; the
  widget names the real source (`Nasdaq` / `Alpha Vantage`). Verified live: 77
  real rows. Nasdaq session values (`time-pre-market` / `time-after-hours`) and
  parenthesised negative EPS (`($1.08)`) are parsed. If a key exists but is
  rejected/limited, it also falls through to Nasdaq. 3 new tests.
- **Workspace** — Fixed being stuck in edit mode. The toolbar/Done buttons used
  `setEditMode(!workspace.editMode)` — a render-time closure, so two toggles
  before a re-render acted on a stale value and left edit mode on. Added
  `toggleEditMode()` which reads the store's current value at call time; the
  toolbar Done button now also shows a check icon. docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center / Earnings** — Added an **Earnings Calendar** widget.
  `src/lib/earnings.ts` (server-only) fetches Alpha Vantage
  `EARNINGS_CALENDAR?horizon=3month` using the existing provider-key vault
  (`ALPHAVANTAGE_API_KEY`); the key never reaches the browser. `getEarningsCalendar`
  caches 6h (shared in-flight, serve-stale-on-error) and returns an explicit
  `unavailable` state with a reason on a missing key, timeout, HTTP error, or a
  JSON rate-limit/notice body. New route `GET /api/earnings`; the widget
  (`widgets.tsx`, registered as `earnings-calendar`, topic `earnings:calendar`)
  shows company, ticker, date, BMO/AMC (maps `pre-market`/`post-market` too),
  EPS estimate, Today/Tomorrow/This Week/3-month filters, loading/empty/error
  states, source + last-updated, and opens a row's symbol on the chart via the
  command store. 5 parser tests. docs updated: `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`

- **Command Center** — ChatDock minimized pill is now draggable. It defaults to
  the viewport bottom-right corner (it was anchored to the centred column, so it
  sat mid-right) and can be dragged anywhere, with the position persisted
  (`be_chat_dock_pill_pos_v1`) and re-clamped on resize. Click restores; a drag
  moves it.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center** — ChatDock float fix + minimize option. The visibility gate
  no longer uses an `IntersectionObserver` on a zero-size sentinel (which made the
  composer vanish mid-scroll — it looked like it scrolled with the page); it now
  reads the keep-alive panel's `display` via `MutationObserver`
  (`[data-keepalive-panel]`). The composer is a true viewport-fixed overlay (no
  reserved `pb-28`). Added a persisted **minimize/restore** pill
  (`be_chat_dock_minimized_v1`) separate from the transcript expand toggle, so
  the user decides small vs big.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center** — Added the floating **ChatDock** assistant composer.
  `components/chat/chat-dock.tsx` is a Gemini-style bottom-centre bar: collapsed
  it is just the composer, and the transcript expands ABOVE it once there is a
  conversation. It reuses the existing chat stack (`ChatHistory`,
  `getAgentProvider()`, `/api/agent/research` for research intents) so there is
  one chat implementation. It owns its own localStorage conversation
  (`be_chat_dock_v1`), portals to `<body>` at `z-[90]` (above the fullscreen
  overlay), and is `data-nodrag` — but deliberately NOT `data-keyboard-overlay`
  (an always-on surface must not block page shortcuts; the focused input already
  suppresses them). A visibility sentinel gates it on the Command Center being
  the ACTIVE keep-alive tab (a body portal is not hidden by an ancestor
  `display:none`). The provider pill shows the REAL configured provider label,
  never a fabricated model. `ChatHistory` gained a `compact` variant.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Aurora / Fullscreen** — Fixed the missing Aurora glow in Command Center
  fullscreen. The overlay portals to `<body>` at `z-[80]`, above the app shell's
  Aurora (`z-0`), so it covered the glow. Extracted the glow into a reusable
  **`<AuroraGlow>`** (`components/layout/aurora-glow.tsx`) that owns the
  market+news sentiment subscription and user palette; the shell and the
  fullscreen overlay both mount it (fullscreen renders its own above the
  translucent backdrop). Removed the duplicated sentiment wiring from
  `stock-chat.tsx` and added a dedicated `aurora:news-score` topic so the glow no
  longer depends on the news screen emitting a callback.
- **Command Center** — Shipped-default board mechanism. `default-board.ts` holds
  `DEFAULT_BOARD_JSON` (paste a Command Center → Export layout) so a curated
  arrangement becomes what every new user downloads into and what Reset returns
  to; validated through `normalizeLayout` so a bad/unknown-widget paste falls
  back to the persona template instead of shipping holes.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Charts / Command Center** — Fixed blank charts, maps and heatmaps. A
  `defaultHeight` card was rendered as `min-height` only, so a frame widget's
  body (`flex-1` with `absolute inset-0` / `h-full` children) had no definite
  height and the ECharts canvas collapsed to **0px** (verified: 687×0 → 687×314
  after the fix). `cardStyle` now gives a `defaultHeight` card a definite
  `height`; `minHeight` stays a grow floor for tiles. Widgets added from the
  library now carry their intrinsic sizing too (`ops.addWidget` /
  `addWidgetToNewSectionAt` take a `sizing` hint), so a fresh chart/map is never
  added collapsed.
- **Command Center** — Added three personas (12 total): **Risk Desk**,
  **Trader Pro** (dual charts) and **The Research Desk**. Layout tabs are now
  **drag-to-reorder** (`TabBar` `onReorder` + `useMarketViews.reorder`), on top
  of the existing drag/click widget arrangement and double-click rename.
  2 new tests. docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Fixed empty layouts after the persona rename.
  The nine personas got new ids (`trader` → `tape-reader` …) but stored v7
  dashboards/market layouts still carried the OLD `templateId`, so
  `getDashboardTemplate` returned `undefined`, `buildMarketViewLayout` received
  no centre base, and **only the side rails rendered**. Added
  `LEGACY_TEMPLATE_IDS` + `resolveTemplateId` so old ids resolve, a blank-layout
  self-heal in `use-workspace`, and bumped storage to **v8**
  (`be_dashboards_index_v8` / `be_ws_dashboard_v8_`) to reseed existing users.
  4 new tests cover every legacy alias building a non-empty centre.
  docs updated: `docs/ARCHITECTURE.md`

- **Workspace / Command Center** — Persona variety, resizable side panels, and
  the widget-fit fix.
  - **Widgets now fit.** Auto cards split into two sizing modes:
    `defaultHeight` (a FRAME whose body stretches — charts, maps, live video,
    scrollable tables/feeds) and `minHeight` (a floor under content that GROWS —
    tiles). The renderer keys its body class off this (`isDefiniteCard`), so
    frame widgets no longer collapse to a `flex-basis:0` body, and the hardcoded
    `minHeight:620` on the Eclipse chart is gone. `WidgetPlacement.defaultHeight`
    added; `normalizeLayout` preserves it.
  - **Personas redesigned + renamed.** The nine templates are now genuinely
    different SHAPES, not reshuffles: Tape Reader, The Desk (dense 4-track),
    The Allocator, Rates Desk, Chain Desk, FX Desk, The Screener, Map Room,
    Newsroom. Bands can override a widget's frame height (`{ id, h }`) for
    deliberate asymmetry.
  - **Resizable left/right panels.** Drag the vertical handle between a side
    zone and the centre to set its width (180–520px); persisted per layout in
    `WorkspaceLayout.zoneWidths` via `ops.setZoneWidth`. Works in normal and
    edit mode.
  - **Nine dead widgets wired to real data:** Agent Errors (agent runs),
    Candle Chart (ECharts candles on the market's lead symbol), Stock Screener
    (`/api/stocks`), Sparklines (real 1mo price history), Crypto Ticker + Trade
    Tape (`market:indices:CRYPTO`), Geopolitics + Maritime & Trade (Investor Eye
    events by lens), News by Category (`/api/news?category=`). Still honest
    UNAVAILABLE: Recent Files, Web Scraper, Notes, Polymarket.
  25 new/updated tests. docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Replaced the row-band layout grammar with the
  **masonry track board** to eliminate dead gaps. Every default placement now
  sizes to content (`height: null`) with a per-widget intrinsic floor
  (`WidgetDefinition.minHeight` / the composition `WIDGET_MIN_HEIGHT` map), so a
  short widget can no longer sit stranded beside a tall one. A new pure packer
  (`src/lib/workspace/pack.ts`, `rebalanceColumns`/`rebalanceLayout`) balances
  each multi-column section's cards into the shortest track at COMPOSE time;
  user edits commit exactly where dropped (no silent reshuffle). Added the
  removed "Fit height" control (auto is the default); `WorkspaceLayout.version`
  is now `2`. `buildMarketViewLayout`/`composeBoard` replace `composeRows`, and
  the eight persona templates + `defaultFundLayout` are track-board specs.
  Storage reset to **v7** dashboards / **v3** funds / `be_dashboards_index_v7`
  (old keys untouched). 20 new/updated tests. docs updated:
  `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Removed compact mode, added fullscreen, and
  fixed the gappy look of the v4 layouts.
  - **Compact mode deleted** (prop, state, toggle, `Shift+C`, canvas plumbing).
    It forced every card to a fixed 40px height and crushed widget content.
    Cards now size to the widget (auto stretch) or a pinned per-placement height.
  - **Fullscreen mode** added to the Command Center (`Shift+F`, header button,
    `Esc` to exit). The overlay is **portaled to `<body>`** because the app
    shell's glass-card `backdrop-filter` creates a containing block that traps
    `position: fixed` — the same constraint the Chart Workspace already handles.
    Body scroll locks while open.
  - **Gaps fixed:** each side rail is now ONE STACKED section instead of one
    section per tile (the per-tile section padding/gap was the "too many gaps"
    problem). Persona bands were reworked to a short 4-up hero, a full-width
    pinned-height primary visual, and roomy TWO-UP analysis/context bands rather
    than four skinny columns. `composeRows` now also carries **pinned heights**
    and `stack` rows. Storage bumped to **v5** (deliberate reset).
  2 new tests (pinned heights + stacked rails). docs updated:
  `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Workspace / Command Center** — Rebuilt the default dashboard layouts. The
  old generator produced cross-zone duplicates (left/right builders were not
  deduped against the centre, so `watchlist`/`top-movers`/`news-feed` rendered
  twice) and a 5-widget "lead" row that `normalizeLayout` truncated to 4 columns
  on reload — layouts literally changed shape after a refresh. Fixes:
  extracted a pure, tested layout engine (`src/lib/dashboard/layout.ts`) with a
  single `composeRows` that enforces **global first-wins dedupe** and a
  **build-time 4-column cap**; rewrote persona templates as **widget-id specs**
  (no more fragile registry indices that silently repoint when a widget is
  inserted) using a **band grammar** (hero → primary → analysis → intelligence →
  context). Six genuinely distinct personas (Trader, Investor, Macro, Crypto,
  Forex, Quant), all with thin side rails (left = Watchlist only; right =
  asset-class `mp-*` stat tiles) and no widget shown twice. Bumped storage to
  **v4** as a deliberate reset — pre-v4 layouts are not carried forward (v3
  dropped from `LEGACY_INDEX_KEYS`), so everyone reopens into the clean defaults.
  23 new tests. docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Live Intelligence** — The widget users actually found was still the OLD
  `UNAVAILABLE` stub. The `live-tv` ("Live TV / Streams") registry slot was a
  hardcoded `<Unavailable>` stub, and it was left in place when Live Intelligence
  was added as a separate `live-intelligence` entry — so anyone with the slot
  already placed (or finding it in the library first) saw "UNAVAILABLE — data
  source not connected yet." Fixed by **upgrading the `live-tv` slot in place** to
  render the real `LiveIntelligenceWidget` (keeping the id so existing saved
  layouts work), deleting the duplicate `live-intelligence` entry, removing the
  dead `LiveTVWidget` stub, and adding the slot to the Trader persona template
  (index 28, which no template referenced) so new users get it by default.
- **Live Intelligence** — Fixed a real first-paint bug this exposed: the widget
  embedded the unreliable `live_stream?channel=<handle>` fallback *before* the
  resolver answered, rendering a blank frame stuck at `CHECKING`. Built-in
  YouTube channels now **wait for the resolver** (a "Checking live status…"
  state) instead of mounting the fallback, so the first frame is always the
  playable `/embed/<resolved-id>`. Added a `COULD NOT CHECK STREAM` state for a
  resolver failure, distinct from a resolved `CHANNEL OFFLINE`.
  Verified in a real browser: `CHECKING → LIVE`, iframe
  `/embed/QB5BNdBFujE`, `<video>` present, and switching to Geo News swaps to
  `/embed/t3fvgmDDmdc` with chip `LIVE`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Workspace** — Added a **left side zone** to the widget workspace so the
  Command Center reads as a three-column dashboard instead of one wide grid. The
  zone model is now `left | main | right` (the old `rail` is mapped to `right` on
  read — no storage bump), rendered under the same `DndContext` and one Customize
  surface. New `setZoneHidden` op + **Left panel / Right panel** toggles in
  Customize let users *remove* a side panel without deleting its widgets
  (`hiddenZones` persists, so re-showing restores the exact arrangement). The
  left column ships populated (Watchlist / Top Movers / News Feed, asset-class
  aware) via `buildLeftSections` + `ASSET_LEFT`. Command Center is denser by
  default (compact rows, trimmed header). Existing layouts migrate automatically.
  5 new tests (legacy-rail mapping, hiddenZones normalization, setZoneHidden).
  docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Live Intelligence** — Fixed the "STREAM UNAVAILABLE" bug. Root cause, verified
  in a real browser against live YouTube: the widget embedded
  `youtube-nocookie.com/embed/live_stream?channel=<UC>`, which YouTube renders as
  **"This video is unavailable"** for most channels that *do* have a live
  broadcast. Two independent findings, both load-bearing:
  - `/embed/<resolved-video-id>` plays correctly where `live_stream?channel=`
    fails (confirmed: Sky News, DW News, Geo News, Bloomberg all "unavailable"
    via live_stream, all playing via the resolved id). Live ids rotate, so they
    cannot be hardcoded.
  - YouTube's `/channel/<UC>/live` page silently omits the canonical live video
    for many channels whose `/@handle/live` resolves correctly — so resolution
    now tries the handle first.
  Added a **server-side, cached resolver** (`live-resolver.ts` +
  `GET /api/live-streams`, 3-min TTL, shared in-flight guard, globalThis-anchored
  like the Investor Eye cache) that reads YouTube's own page metadata
  (`canonical watch?v=` + `"isLive":true` + `playableInEmbed`) to classify
  `live` / `offline` / `unavailable` / `unknown`. The widget embeds the resolved
  id, exposes honest `LIVE`/`OFFLINE`/`CHECKING` status (never a fabricated
  LIVE), shows a `CHANNEL OFFLINE` state with Check Again, and surfaces live
  status dots in the channel manager. Registry corrected too: the old
  `al-jazeera` id was actually Al Jazeera *Arabic* (English now
  `UCNye-wNBqNL5ZzHSJj3l8Bg`); added `@handle` for every channel; added
  verified Moneycontrol, CNBC Awaaz, India Today, PTV News; removed unverified/
  permanently-offline entries from the default-on set. 26 new tests.
  docs updated: `docs/ARCHITECTURE.md` (Live Intelligence section),
  `docs/NAVIGATION.md`
- **Live Intelligence** — Verified source registry against live YouTube. 20
  channels resolved and played: Bloomberg Television, CNBC, Yahoo Finance,
  Moneycontrol, Sky News, Al Jazeera English, DW News, Euronews, NHK WORLD-JAPAN,
  CNA, ABC News (Australia), CNBC-TV18, ET Now, Zee Business, India Today, WION,
  CNBC Awaaz, Geo News, Samaa TV, PTV News. Five official channels were **not**
  broadcasting at test time and are shipped disabled with `lastKnownStatus:
  'offline'` (Fox Business, France 24 English, TRT World, NDTV Profit, ARY News,
  Dunya News) — they may return, and the resolver re-checks every 3 minutes.
  Not added at all: Sky News' old id, Bloomberg Technology, CGTN America (no
  live broadcast observed).
  no doc change — covered by the architecture section above.
- **Build** — Learned (again) not to run `next build` while `next dev` shares the
  same `.next` directory: it produced `Cannot find module './NNNN.js'` and an
  empty Command Center. Clearing `.next` and restarting dev fixed it; no source
  change.
  no doc change — local build-artifact contention.

## 2026-09-17

- **Investor Eye** — Fixed the `Cannot read properties of null (reading '0')`
  crash when the Investor Eye **map** is embedded in a dashboard widget. The
  ECharts geo `View` dereferences a null matrix when `setOption` runs against a
  **zero-size container**; the full-screen map always has an explicit height, but
  a widget card can mount a frame before flex layout resolves its height.
  `WorldMap` now initialises through a `hasDrawableBox()` guard and lets its
  ResizeObserver trigger init once the box is real (the previous observer only
  resized an already-created chart). Reproduced directly against echarts: 0×0,
  0×400 and 400×0 throw; 1×1 and any real size are fine.
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Command Center** — Added an **Investor Eye Map** widget: the same interactive
  world map / 3D globe the Investor Eye screen renders, embedded in the dashboard
  grid. It reuses the SAME DataHub state topics + `buildAllLayers()` (no second
  fetch path, no fabricated data) and the shared `useInvestorEyeStore`, so
  selection and layers stay in sync with the full screen. The map chunk is
  `next/dynamic`-split, so a dashboard without this widget never loads
  ECharts/`echarts-gl`. Configurable `range` (1H…30D); a header **Open** button
  navigates to the Investor Eye tab for the detail dossier. Registered beside
  `investor-eye` in `DASHBOARD_WIDGETS` (templates are index-based).
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Workspace** — Fixed two editor bugs. (1) Column width resize reverted to its
  pre-drag width: the handle rewrote a single column's weight, which the 1..6
  clamp saturated, and the height-resize commit measured a stale DOM value after
  clearing the preview style. The boundary handle now moves the shared edge —
  growing one column while shrinking its neighbour atomically via the new
  `setColumnWeights` op, so the section total is invariant and the drag is fully
  reversible left↔right; weight range widened to 0.3..12 for a usable aspect
  ratio; the height commit now uses the tracked pointer delta.
  (2) Adding a column to a section (`setColumnCount`) ran `pruneLayout`, which
  deleted the still-empty section the user had just created — so "add a
  three-column section" vanished. `setColumnCount` no longer prunes empty
  sections (they are legitimate user-created drop targets, as `createSectionAt`
  already preserved).
  no doc change — UI bug fixes and internal op addition, contracts unchanged
  (`setColumnWeights` is additive; `WorkspaceColumn.weight` still a number).
- **Live Intelligence** — Added a **Live Intelligence** Command Center widget: a
  terminal-style live news player for financial, market, business and
  geopolitical broadcasters, with an in-card channel manager (enable/disable,
  set default, filter, search, and advanced custom sources). New modules:
  `live-channels.ts` (23-channel registry — every YouTube id resolved from the
  network's own page, never invented — plus `channelEmbedUrl`/`safeEmbedUrl`
  host-allowlist and `parseCustomSource`), `live-intelligence-store.ts`
  (localStorage selection store reusing the ribbon/watchlist storage-event
  pattern), and `live-intelligence-widget.tsx` (player + loading/offline/error/
  empty states). Registered as a normal widget appended last in
  `DASHBOARD_WIDGETS`, so move/resize/config/persist come from the existing
  workspace kernel — no second framework, no new dependency (YouTube embed uses
  a plain iframe; HLS was deliberately not added since no verified source needs
  it). 27 tests.
  docs updated: `docs/ARCHITECTURE.md` (new "Live Intelligence" section),
  `docs/DECISIONS.md` (ADR-015), `skills/ARCHITECT.md` (ADR-012–015 backfilled
  from `DECISIONS.md`), `docs/NAVIGATION.md`
- **Live Intelligence** — Media widgets now own their teardown (ADR-015). The
  shell keeps visited tabs MOUNTED and hidden with `display:none`, and
  `WidgetDefinition.lazy` is declared but never read, so a playing iframe would
  stream forever on an unwatched tab. The widget uses an `IntersectionObserver`
  (catches `display:none` ancestors and scrolled-off cards) plus a
  `visibilitychange` listener (browser tab) to unmount the player, re-mounting
  on return. Neither signal alone is sufficient.
  docs updated: `docs/DECISIONS.md` (ADR-015), `skills/ARCHITECT.md`
- **Screener** — Split the `market-overview.tsx` monolith: 4,599 → 2,593 lines
  (273 KB → 140 KB). Extracted `use-global-markets.ts` (Global Markets fetch +
  persisted prefs + pointer drag engine), `market-overview-global-markets.tsx`,
  `use-market-tabs.ts` (forex/commodities), `market-stock-tables.tsx`,
  `market-fund-etf-tables.tsx`, `market-tables.tsx`, `market-format.ts`
  (price/cap/time formatting) and `market-loaders.tsx` (table loaders). Pure
  mechanical extraction — no behavior or contract change; `tsc`, all 1157 tests
  and `next build` pass.
  docs updated: `docs/NAVIGATION.md`, `skills/ARCHITECT.md`, `skills/REMEMBER.md`
- **News** — Rewrote the sentiment classifier (`src/lib/sentiment.ts`): phrase
  patterns now disambiguate context words (bare "record" is neutral, "record
  loss" is bearish, "record high" bullish), punctuation is normalized so
  "sell-off"/"record-breaking" reach their phrases, dead zero-weight lexicon
  entries were removed, and concessive connectors ("despite", "although") no
  longer negate (they inverted correct headlines). Negation now covers a
  dedicated negator set. 10 unit tests.
  no doc change — the `src/lib/sentiment.ts` reference already in `DATA-FLOW.md`
  is still correct; behavior improved, contract unchanged.
- **Symbols** — `getTradingViewSymbol()` fixes: the Yahoo suffix list is now one
  shared `stripExchangeSuffix()` helper (was duplicated with drift across the
  quote/price-history routes, with duplicate `.AS`/`.TO` branches), suffix-only
  resolution works without a `market` hint (`0001.HK`→`HKEX:0001`, `7203.T`→
  `TSE:7203`), the crypto branch no longer produces `BINANCE:BTC-USDT` for
  `BTC-USD`, and the explicit FX mappings (`EUR=X` etc.) are reachable again —
  the generic `=X` branch had turned them into a non-pair `FX_IDC:EUR`. 12 tests.
  no doc change — internal mapping correction; the contract is unchanged.
- **Docs** — `skills/ARCHITECT.md`: corrected stale relics against the code —
  ADR-001 "no DB" and ADR-002 "live news" claims, the missing Investor Eye /
  connector routes and DB models in the architecture map, the pre-JDDS
  "Yahoo Finance + HTML fallback" scraper description, and the ~1900-line
  screener note (now the current module split).
  docs updated: `skills/ARCHITECT.md`
- **Build** — Every page appeared dead: a stale/corrupt `.next` build cache made
  `next start` serve a 500 and left the boot overlay stuck at 1% (it failed to
  load `./6764.js`). Code was sound (`tsc` + all 1140 tests pass); removing
  `.next` and rebuilding restored all tabs with zero console errors.
  no doc change — stale local build artifact, not a source change.
- **Investor Eye** — The `black` globe was too dark to read (a near-black texture under `lambert` collapsed into a featureless ball). Its palette is now mid-grey — ocean `#1a1c20`, land `#4b5058`→`#5a606a`, brighter coastline — lit with a higher ambient (0.85) and no shadowing. Measured mean luminance 55 vs 14 before; land now reads 84–119 against an ocean of 38.
- **Investor Eye** — Added a **STARS ON/OFF** toggle to the map view controls (`showStars`, persisted and captured in saved views). The starfield is UNMOUNTED rather than hidden so its rAF loop actually stops; with stars off a skin-matched CSS backdrop paints the sky.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`
- **UI** — The header **price ribbon** is now wider, background-free, and fully
  customizable. It fills the middle of the header (search stays fixed at `38%`),
  drops the card/glass fill so it reads as bare market chrome, and scrolls
  **left→right** (`from -50% to 0`, still seamless, hover-pause, reduced-motion
  aware). A gear opens a portaled popover to add any symbol (same DB
  autocomplete as the pin inputs), remove chips, or reset to defaults; the list
  is persisted in `src/lib/ribbon/store.ts`. Data routing is split by family:
  catalog commodities/FX from `market:commodities`/`market:forex`, everything
  else from a dynamic `/api/quote` topic. Extracted `src/lib/market-catalog.ts`
  as the single source of truth for the commodity/forex symbol lists (now also
  consumed by both API routes).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Investor Eye** — Added a **surface skin switch** (`MapSkin`: `black` | `glow`)
  beside the MAP/GLOBE toggle, in both the hero header and the full-page dock, via
  one shared `map-view-controls.tsx`. `glow` (default) is a blue lit planet —
  translucent blue continents over the starfield, cyan coastlines, blue globe
  ocean/land, emission aura + bloom; `black` restores the first-draft flat
  terminal surface (no glow, no aura, still sky). Persisted, and captured in saved
  views. Globe textures are now keyed by skin (the old cache guard silently kept
  the blue planet after a switch).
- **Investor Eye** — Fixed the **pin glyphs**: earthquake/portfolio/risk drew as
  solid blobs because their cut-outs wound the same way as their outer shape
  (nonzero fill rule) and circles were drawn as a single near-full arc (renders
  off-centre); the catch-all `events` dot sat above the category layers
  (`zIndex` 30 > 25) and buried them; `wave`/`exchange` subpaths overlapped.
  Regression tests now assert the winding and the z-order.
- **Investor Eye** — Made the starfield **actually alive**: meteors spawn from
  0.6s then every 3–8s (was 6–18s, so the sky looked static), and the loop uses
  real elapsed time instead of an assumed 60fps (clamped so a backgrounded tab
  cannot teleport stars).
  docs updated: `docs/investor-eye-architecture.md` (§5n new; §5m marked partly
  superseded), `docs/NAVIGATION.md`
- **UI** — Added a **live price ribbon** to the app header beside the global
  search trigger. It is a thin view over the existing DataHub topics
  (`market:indices:US`/`CRYPTO`, `market:commodities`, `market:forex`) — no new
  API, polling, or cache. Missing symbols are omitted rather than placeholder-
  priced; clicking a quote dispatches a chart destination on the command bus.
  Marquee styles live in `globals.css` (untransformed glass wrapper + two-copy
  `-50%` track, disabled under `prefers-reduced-motion`).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Command Center** — Added an **Investor Eye** widget to the dashboard widget
  catalog, so the normalized world-state event feed is available on the Command
  Center without switching to the Investor Eye screen. It is a thin view over the
  SAME DataHub state topics the full screen consumes (`investor-eye:state:<hours>`)
  — no second cache and no fabricated data; a failed/unavailable topic renders
  `UNAVAILABLE`. Configurable `range` (1H…30D) + `lens` (all/conflict/energy/trade/
  hazards). Registered at the end of `DASHBOARD_WIDGETS` because the persona
  templates address widgets by array index.
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Command Center** — Fixed the Investor Eye widget reading as broken while the
  first world-state assembly runs: the header status chip showed a red
  `UNAVAILABLE` dot during the (up to ~15s) cold build even though the body said
  "Loading world state…". The chip now shows a neutral `LOADING` state until the
  topic settles, and only then reports LIVE/CACHED/UNAVAILABLE.
  no doc change — presentation-state fix, contracts unchanged.
- **Investor Eye** — The globe gets a real visual system, and fixing it exposed two
  bugs that were blocking the whole screen.
  - **Look.** The globe was a flat, washed-out blue sphere. The surface texture now
    carries the design: near-black gradient ocean, dark land, a blurred coastline
    bloom, and a deterministic city-light stipple. Added a canvas starfield (three
    depth tiers + two nebula washes), a cyan `atmosphere` rim, and much lower
    ambient lighting — a high ambient was what turned the planet into a bright blue
    ball. Pins on the globe are now drawn **three times** (wide faint halo, tight
    coloured halo, white-hot core); the first attempt used one colour for core and
    halo and rendered as dark-centred donuts. 2D pins got a dark contrast ring and
    a severity-sized glow; trade routes got a translucent glow pass. Auto-rotation
    is deliberately off — the pins are click targets.
  - **Bug: a map-local loader covered the entire app.** `WorldMap` used
    `TopLoader`, which portals to `document.body` at `z-[45]`, so a still-loading
    map froze the whole application on a `95%` overlay (sidebar included). It is
    now scoped to the map box, with a 20 s globe-init ceiling that falls back to
    the flat map. Recorded as ADR-014.
  - **Bug: `ReferenceError: TopLoader is not defined`.** Replacing the loader left
    one stale reference inside a `useMemo`; the error boundary then left the frozen
    frame on screen instead of surfacing an error.
  - **FIRMS reliability.** The 24h global CSV occasionally exceeded the transport's
    10 s cap, silently emptying the hazard layer for a whole cycle. Added one
    bounded retry, for transient transport errors only.
  - **Verified live:** all 4 sources healthy, 794 events / 21 markets, and the
    Shipping/Energy/Commodities layers toggling correctly.
  docs updated: `docs/investor-eye-architecture.md` (§5m), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-014)


- **Charts** — Replaced oversized Settings previews with fixed-height illustrative candles/volume, a restrained area line, and an ordered three-color treemap; all configured colors remain visible without changing widgets, palettes, or data. Removed redundant preview revision state.
  no doc change — visual-only Settings refinement, contracts unchanged.

- **Keyboard** — Fixed a real shortcut conflict: the Agentation visual-feedback
  toolbar registered a `document`-level handler that unconditionally claimed plain
  `L`, `P`, `H`, `C`, `X` and `S`, so `Shift+L` (focus layouts / grid menu),
  `Shift+C` (compact rows) and screen `S` (local search) never reached the app.
  It is now opt-in via `NEXT_PUBLIC_AGENTATION=1`. The widget library and widget
  config drawers now close with Escape, which they previously ignored while still
  blocking page shortcuts. Verified in Chrome against a running dev server: 20/20
  keyboard checks pass (function keys for every screen, `Ctrl+/` help, `Shift+E`,
  `Shift+W`, `Shift+N`, `Shift+L`, `S` local search, Escape layering).
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **Keyboard** — Faster workflows, and the shortcut help panel now scrolls.
  - **Scroll fix.** The `Ctrl+/` help panel could list more shortcuts than fit,
    but the results region had no working scroll area (a grid child without
    `minmax(0,1fr)` cannot shrink), so lower entries were unreachable. The dialog
    is now an explicit grid with a `minmax(0,1fr)` scroll row; verified overflow
    scrolls in Chrome.
  - **Action palette.** `Ctrl+K` now *does* things, not just navigate. Real
    commands: set a price alert for a symbol, add a symbol to the watchlist,
    open a chart, open the Journal or Journal Calendar, show today's economic
    events, open/export a specific fund, export all portfolios, and jump to any
    Settings section. Every command reuses an existing handler — the previously
    dead `createQuickAlert` / `addToWatchlist` / param-command path is now wired,
    and results state their target. No delete/reset command exists by design.
  - **List navigation.** New shared `useListNavigation` hook (stable-ID selection,
    never index) wires `↑/↓` + `J/K`, `Home/End`, `Enter`, `Escape`, and `[`/`]`
    into news, screener stocks/crypto, alerts, journal trades, and the Investor
    Eye feed. Typing is never hijacked and only the visible screen responds.
  - **Chart keys.** Focused charts gain `V` volume, `0` reset zoom, `=`/`+`/`-`
    zoom, and `Alt+←/→` pan. Timeframe/indicator/compare pickers were skipped:
    their open-state is internal to toolbar menus, so there is no handler to call.
  - **Sub-tabs and back.** `Alt+1..Alt+8` select Journal sub-tabs, `Alt+1..3` the
    Economics modes (with `Alt+0` for the last), and `Alt+←` steps back through a
    bounded 20-entry screen history — the app has no router, so this is its only
    back affordance. History is in-memory and shell-tab only.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `docs/OVERVIEW.md`
  (keyboard-ownership section), `docs/QUICKSTART.md`.

## 2026-09-16

- **Chart Workspace** — Removed the green box that appeared around the whole page
  in full page / fullscreen mode. Root cause: `globals.css` sets
  `outline-color` on `*` (via `@apply outline-ring/50`), and the full-page and
  fullscreen overlays are keyboard FOCUS SINKS — they are programmatically
  `.focus()`ed so their shortcut scope is active. The moment `:focus-visible`
  matched (any keyboard interaction: Tab, Ctrl+Enter, or F11 as reported), the
  browser painted its default focus ring around the `fixed inset-0` element in
  that inherited colour. Added `outline-none` to both overlays and the workspace
  root; verified no viewport-sized outline remains.
  no doc change — bug fix, no contract or architecture change.

- **Portfolio** — Repaired `fund-manager.tsx`, which had been corrupted by a bad
  global `p`/`P` → `a` replacement (the file contained zero `p` characters, e.g.
  `import` → `imaort`), breaking `/` and every API route with 500s. Reconstructed
  from HEAD and re-applied the seven intentional edits layered underneath
  (chart-palette benchmark colours, `usePageShortcuts` + `Shift+N` create-fund
  shortcut, keyboard scope on the root), then fixed a real type error in that
  work: `palette.series` → `palette.lines.series`. Diff vs HEAD is exactly the
  15 insertions / 7 deletions of the intended change, with no corruption residue.
  no doc change — corruption repair, intent preserved.

- **Build** — `devIndicators: false` in `next.config.ts`. The Next.js dev-tools
  indicator floats over the bottom-left corner and intercepts pointer events,
  which blocked automated UI checks against the controls underneath it.
  no doc change — dev-only tooling.

- **Charts** — Palette is now sectioned per widget type (candles / lines / heatmap) so presets and edits no longer recolor everything at once. Settings → Charts shows a dedicated card per section with its own preview, swatch presets, and per-section reset; storage moves to `be_chart_palette_v2` (old v1 ignored). All consumers migrated to `palette.candles.*` / `palette.lines.*` / `palette.heatmap.*`.
  docs updated: `docs/CHANGELOG.md` (contract change noted here; no separate doc page covers palette internals)

- **Settings / Investor Eye** — A dedicated API-keys menu, working data layers, and
  readable map pins. Three separate problems, all reported against the real UI.
  - **API Keys menu.** Settings had no place to enter a credential — the connector
    wizard only accepts an arbitrary REST endpoint. New `provider-keys.ts` + a
    `settings.api-keys` section list all 24 credentials BlackEclipse can consume,
    grouped by what they power (AI / Market / Crypto / Economics). Keys are
    encrypted with the existing AES-256-GCM path and stored in `SystemConfig`;
    the value is never returned to the browser (only a masked hint). "Test" makes
    a real request and reports the real HTTP status — an invalid key returns 401,
    verified live, rather than a success inferred from the key existing. A key set
    by an environment variable is shown as authoritative and read-only, and
    `applyStoredKeysToEnv()` copies stored keys into `process.env` at boot so
    every existing consumer works unchanged. Removing a stored key only clears a
    variable this process populated from the vault, so a deployment env var can
    never be destroyed.
  - **Layers were showing a fraction of the data.** `classify.ts` assigns ONE
    event type but MANY channels, and the domain layers matched on type only, so
    an event typed `conflict` carrying the Shipping channel was invisible to the
    Shipping layer. Measured live in a 24h window: 11 shipping-typed vs 28 with
    the Shipping channel, 29 vs 46 for energy. Layers now match type **or**
    channel, and two new layers (`shipping`, `commodities`) plus channel-driven
    trade lines surface the physical-economy signal that was already in the
    database.
  - **Pins.** The old markers were 6–13px flat dots with a thin border and read as
    noise on the dark map. Pins are now larger (8–18px), carry a dark contrast
    ring so neighbours never bleed together, and a severity-sized coloured glow so
    urgency is visible before hovering.
  - **Also fixed:** the dev server had a stale Prisma client from before the
    `category` column existed, so FIRMS rows silently failed to persist while the
    map still showed them. Restarting is the fix; `persistEvents` swallowing the
    error is why it was invisible.
  docs updated: `docs/investor-eye-architecture.md` (§5l), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`, `docs/DECISIONS.md` (ADR-013)

- **Workspace / Charts** — Add scoped workspace actions and chart focus ownership; prevent drawing keys from reaching other charts or deleting panels, guard typing and hidden screens, and confirm keyboard panel removal. no doc change — existing shortcut and workspace contracts reused.

- **Charts** — Fix broken palette integration left by interrupted edits: undefined `UP`/`DOWN`/`primary`/`colors`/`palette`/`GRADIENT`/`cn` references in journal charts, economics panel, Monte Carlo, and heatmap widgets crashed the build when selecting colors. Journal charts, economics panel, Monte Carlo, and heatmap treemap now consume the shared chart palette with live update dependencies; typecheck clean, 1,078 tests pass. no doc change — internal repair of in-flight feature, contracts unchanged.

- **UI** — Wire scoped screen shortcuts to existing creation forms, search, filters, customization and refresh; guard Investor Eye navigation against hidden screens, editing, dialogs and extra modifiers. no doc change — existing keyboard hook contract reused, no architecture or setup changes.

- **Keyboard** — Ship configurable function-key defaults, Ctrl/Cmd+/ searchable help and shared exact-match, visible-scope dispatch to prevent hidden-screen and typing conflicts; preserve customized sidebar settings and reserve F11. Tests and typecheck pass; lint reports warnings only. docs updated: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`.

- **Charts** — Add eight palette presets (Black & white, Silver, Sunset, Arctic, Forest, Candy, Neon, Blue & orange) and preview swatches for more visual variety; monochrome uses charcoal instead of invisible black on dark charts. no doc change — presentation presets only, storage and chart contracts unchanged.

- **Charts** — Native Eclipse charts subscribe to palette changes and resolve indicator, structure, and comparison colors at render time without resetting zoom or rewriting saved drawings; remove the permanent brand-color cache. no doc change — existing provider and state contracts unchanged.

- **Investor Eye** — Data-source governance and NASA FIRMS. The spec's licensing
  requirement had no home, and the hazard layer had a single source.
  - **Source catalog.** New `source-catalog.ts` records licence, licence/terms
    URL, commercial-use, API-key requirement, attribution, rate limit and
    freshness per source. It is separate from the adapters on purpose — a licence
    question should not require constructing a fetcher. Tests assert every
    registered source has an entry (and vice versa) and that `requiresApiKey`
    agrees with the adapter, so a source cannot ship without declaring its terms.
  - **FIRMS connector.** Keyless global archive CSV (the Area API needs a
    `MAP_KEY`, which would break zero-config). ~25,600 raw single-pixel
    detections become ≤400 grid clusters at ingestion, carrying real detection
    counts and summed FRP. Three bugs fixed while building it: the grid needs a
    `cos(lat)` correction or polar fires fragment away; empty CSV cells must be
    rejected before `Number()` turns them into 0; and a feed URL must not be
    stamped as a source `url`, because `dedupKeyFor` treats source URLs as article
    identity and all 400 clusters collapsed to one event.
  - **Exact country attribution.** `admin-boundaries.ts` runs point-in-polygon
    against the same Natural Earth GeoJSON the map already ships. Centroid
    matching attributed 62/400 live fire clusters; point-in-polygon 167; using the
    boundary asset's own ISO2 when the curated gazetteer lacks the country, 397.
  - **Hazard split.** A provider-stated `category` (`earthquake`/`fire`)
    separates the `fires` layer from `weather`, refuses to merge different
    categories during clustering, and is exclude-based so pre-existing rows keep
    their original layer with no migration.
  - **Health UI.** `/api/investor-eye/health` joins governance onto `SourceRun`
    accounting and returns attribution lines; `SourceHealthPanel` renders the
    spec §19 columns and flags a runnable-but-undeclared source as a gap.
  docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Journal** — Calendar follow-ups. The contribution heatmap was too small and
  the month grid only existed on the Calendar tab.
  - **Heatmap is now big.** `MiniCalendar` gained a `fill` mode: the grid spans
    the card, cells stay square via `aspect-ratio`, and a `maxCell` cap (30px)
    stops a very wide card from producing ~50px squares that dominated the page.
    Default widened to 39 weeks / nine months. Measured 30×30 cells across a
    1316px grid (was 11px cells in a 595px half-width grid).
  - **Month calendar now on the Overview too**, via a new `MonthCalendarCard`
    (its own prev/next + month stats) so both tabs show year AND month views.
  - **Fixed a timezone bug in the month label.** `toLocaleString` without a
    `timeZone` formats in the browser's local zone, so `Date.UTC(2026, 8, 1)`
    (Sept 1 UTC) rendered as **"August 2026"** west of Greenwich — the label sat
    a month behind the grid it described. New `src/lib/journal/dates.ts`
    (`formatMonthLabel` / `formatDayLabel` / `weekdayShort`) formats in UTC, and
    the month card now opens on the most recent trade's month rather than the
    local clock. 7 tests pin this across five timezones.
  docs updated: `docs/NAVIGATION.md`

- **Investor Eye** — Situation recurrence and honest corroboration.
  - **Situation timeline** (`situations.ts`, pure). A single event in isolation is
    not intelligence: an explosion near Hormuz means something different when it
    is the fourth incident there this week. Events are grouped into SITUATIONS by
    type + country, and the dossier shows the count, span, peak severity, a
    severity trend and whether it is escalating.
    - **Bucketed by COUNTRY, not place string.** Measured on live data, bucketing
      by raw place fragmented one situation four ways ("US", "United States",
      "Washington", "Washington, D.C.") because providers disagree on
      granularity.
    - **And then labelled by country, not by the top place.** With country
      bucketing the first working version labelled 147 US conflicts as
      "Washington, D.C.", which implied they were all there. The label is now the
      country (what the count actually covers), with the most-common place and
      the number of distinct places offered as separate context — "140x conflict
      in United States · across 61 places, most often Washington, D.C.".
    - "Escalating" requires **3+ occurrences and a genuinely rising trend** (two
      points is a comparison, not a trend) and is explicitly described as a
      description of the trend so far, not a forecast.
  - **Corroboration badge now counts distinct OUTLETS.** After the
    article-identity fix one article can legitimately back several captured
    sources, so a raw `sourceCount` overstated corroboration. The badge and the
    Sources block now report distinct outlets and distinct article URLs, and say
    "Multiple citations of the same article — one outlet" when that is the case.
  - `GET /api/investor-eye/situations` reads the same stored feed the map uses, so
    a situation can never disagree with the events on screen.
  - 16 new `situations` tests, including the two regressions above.
  - Verified: 952 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
    `jdds.db` NOT committed — no schema change.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Journal** — The journal was empty on every tab. Root cause: it is DB-backed
  (unlike the localStorage portfolio demo), and although a seeder existed it had
  never been run or wired into boot — the committed `jdds.db` held **0 `Trade`
  rows** and two duplicate `JournalProfile` rows from a `getOrCreateProfile()`
  race. Fixed by making seeding real and honest:
  - **`src/lib/journal/demo.ts`** is now the single generator, invoked from boot
    (`instrumentation.ts`) and from `scripts/seed-journal.ts` (now a thin
    wrapper). It seeds ~90 days of deterministic trades so every tab has content.
  - **Provenance, not mystery data.** Added `Trade.source` (`'manual' | 'demo'`)
    and a journal banner that says how many rows are sample data, with a
    one-click "Remove demo data" that deletes ONLY `source: 'demo'` rows. A
    `SystemConfig` marker stops the seeder re-adding what was deliberately
    cleared — verified across a server restart.
  - **Fixed the profile race** so duplicates collapse to the oldest row instead of
    accumulating (2 → 1 in the existing DB).
  - **Coherent risk sizing.** Positions are now `riskTarget / stopDistance`
    against the profile's `accountSize × riskPerTrade`, so risk per trade varies
    gently (CV ≈ 0.10) instead of ~8× across symbols — without this the risk
    analytics (risk consistency, the 1% rule, expectancy in R) were noise.
  - **Mini calendar rebuilt** as a compact GitHub-style week grid: fixed 11×11
    cells with signed R-intensity buckets. Previously the cell had no width class,
    so `grid-cols-10` stretched each one to fill its column and the "squares"
    became large rectangles. Intensity is now shared with the year heatmap via
    `src/lib/journal/intensity.ts`.
  - Verified in-browser: all eight journal tabs render real derived content (e.g.
    "Best session: Asia +19.70R", "Behavioral leak: Revenge −4.03R", expectancy
    +0.26R), calendar cells measure 11×11, zero console errors. 9 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/OVERVIEW.md`

- **Investor Eye** — "Explain this event": the AI analyst, where the question is
  asked.
  - The 7 read-only Investor Eye agent tools already existed but were reachable
    only from the chat, so a user had to leave the event and re-describe it. The
    dossier now has an **Analyst** section that runs the world analyst against
    THIS event's structured record.
  - **Grounded, not generative.** `event-record.ts` renders the event as a
    compact briefing (headline, type, location AND its precision, coordinates,
    countries, actors with readable type codes, CAMEO/Goldstein, text-derived
    channels/commodities/sectors marked as derived, relevance, confidence labelled
    "NOT certainty", sources, description) and the model may also call the
    read-only tools. Absent fields are omitted rather than printed as
    placeholders, which would invite the model to fill the gap.
  - `POST /api/investor-eye/explain` is guarded and rate-limited (12 per 5 min)
    as it drives LLM calls. With no provider configured it returns **503**, and
    the panel says so — it never pretends to work offline (verified: HTTP 503 →
    "No AI provider is configured").
  - The route handler is thin; the prompt-building logic is pure and unit-tested
    (6 tests), because the SHAPE of what the model receives is a correctness
    concern — if actors or provenance silently vanished, the analyst would start
    guessing.
  - Verified: 927 tests pass, eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Where things are plotted is now right, and honest about it.
  - **Policy events were landing in Kansas.** `CountryDef.lon/lat` is a country's
    GEOGRAPHIC CENTROID, so "the Fed raises rates" plotted at the USA centre, and
    "Brazil's central bank cuts rates" landed in the Amazon. Policy, monetary and
    diplomatic news is reported FROM the capital, so `geo-resolve.ts` now prefers,
    in order: a named place → an exact provider coordinate → the CAPITAL (for
    policy event types only) → the country centroid. A new `CAPITALS` table (81
    entries) supplies the anchor without disturbing the centroid, which map fills
    and country highlighting still rely on. `conflict`, `military`,
    `natural_disaster`, `energy` and `shipping` are deliberately EXCLUDED — those
    have a real physical location that is usually not the capital.
  - **Measured on live data:** news-source country-centroid share fell **83% →
    34%**; across all events, `place` anchors rose 11 → 44, `centroid` fell 76 →
    67, and **88 events now correctly anchor to a capital**.
  - **A guess no longer looks like a fix.** Country-centroid points are drawn as
    hollow, dashed, slightly smaller markers, with a legend entry ("country-centre
    only") and a tooltip line stating the location is not a confirmed position.
    The dossier reports it too (`country capital (policy event)` etc.).
  - **Existing rows are upgraded on read.** `reResolveEventLocation` re-derives
    the anchor when an event is loaded, so historical rows pick up the capital
    rule without a database migration — resolution is deterministic and cheap.
    An exact provider coordinate is never second-guessed.
  - **Gazetteer extended** with ~120 places that appear in real headlines: ports
    (Alexandria, Aqaba, Mombasa, Djibouti, Port Harcourt, Novorossiysk,
    Vancouver…), rivers that shape logistics (Danube, Rhine, Yangtze, Mississippi,
    Paraná), and commodity regions (Antofagasta, Fort McMurray, Niger Delta,
    Ordos, Sudbury). The gazetteer test caught that **Djibouti, Somalia and
    Eritrea were missing from the country table entirely**, so Red Sea shipping
    events had nowhere to plot; all three added.
  - 15 new `geo-resolve` tests, incl. deliberate negative cases (a physical event
    must NOT be forced to the capital; a provider fix must never be overridden).
  - Verified: 921 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
    `jdds.db` NOT committed — no schema change (coordinates are derived on read).
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Portfolio** — Added three risk widgets to the fund workspace: **Portfolio
  Heatmap** (treemap — area by position value, colour by day move on the shared
  ±3% gradient, with fullscreen), **Correlation Matrix** (ECharts heatmap of
  pairwise return correlation) and **Risk Matrix** (per-holding volatility, beta
  to the portfolio, and each position's contribution to total risk). All three
  register in `FUND_WIDGETS`, the icon map and the default layout.

  Accuracy work the widgets depend on — the matrix is only meaningful if these
  hold:
  - **Date alignment, not position alignment.** Different markets have different
    trading calendars, so `closes[i]` is not the same day across symbols;
    correlating position *i* against position *i* silently compares different
    calendar days. `src/lib/portfolio/matrix.ts` computes every statistic on the
    **intersection of dates** for the pair concerned. Pairs with <20 shared
    returns render `·`, never a plausible-looking `0.00`.
  - **Correlation is currency-neutral.** Returns are ratios, so native-currency
    closes give identical correlations to USD-converted ones — correct for a
    mixed USD/PKR/INR book with no FX step (documented, including the limitation
    that a currency's own move is a separate exposure).
  - **Risk decomposed properly.** Euler decomposition over the same Σ used for
    the matrix: σ_p=√(wᵀΣw), CTRᵢ=wᵢ(Σw)ᵢ/σ_p, shares sum to 100%. Variance is
    clamped at 0 (pairwise-complete correlation isn't guaranteed PSD) so a
    negative "risk" can never surface.
  - **Fixed a real desync bug** in `use-price-histories`: it filtered `closes`
    but mapped `dates` unfiltered, so any bar with a bad close shifted every
    later date onto the wrong close.
  - **Fixed market resolution.** `marketHintFor` defaulted everything unknown to
    US, so an Indian or UK holding was requested without its exchange suffix and
    returned no series at all. `/api/price-history` now treats the `market` param
    as a hint and, on a miss, asks JDDS which markets list the symbol (one
    indexed query) and retries with the real one.
  - **Fixed currency handling.** `useLiveQuotes` discarded `/api/quote`'s real
    `marketId` and re-derived a USD/PKR binary from a 16-symbol allowlist, so an
    INR holding was valued 1:1 against the dollar. The engine now converts any
    currency at its live `fxToUsd`, falls back to a documented approximation
    table when a rate is missing, and flags the holding `fxMissing` so the UI can
    call that USD value an estimate.

  Verified against an independent Pearson implementation on real series (values
  matched to 3dp) and in-browser on the seeded Core Growth fund: all three
  widgets render, zero console errors. 39 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/OVERVIEW.md`,
  `README.md`

- **Investor Eye** — Article metadata recovery, readable titles, and a
  correction to a claim in the entry below.

  - **Correction.** The entry below says the news-corpus enrichment gave events
    "real headlines" and cites 202 of 461. That number was the count of
    `news`-source events, which are articles and always had headlines — the
    enrichment itself contributed almost nothing. Measured against the live DB,
    the normalized-URL join matched **27 of 2,524 GDELT events (1.1%)**: the RSS
    corpus and GDELT's article set barely overlap. The claim was misleading and
    is superseded by this entry.
  - **The real fix: read the article.** `article-meta.ts` (pure parsing) +
    `article-meta-fetch.ts` (guarded network + cache) fetch a source URL through
    the shared `safeGet` and extract `og:title` / `og:description`, falling back
    to `twitter:title`, `<title>` and `<h1>`. Only the `<head>` is searched so a
    body quoting "og:title" can't masquerade as metadata; bot-walls, consent
    screens and site-name-only titles are rejected. `GET /api/investor-eye/article`
    is guarded (outbound I/O), tries up to 3 source URLs, and caches per URL in
    bucketed `SystemConfig` JSON so **any URL is read at most once, ever**.
    Lazy — fetched when the dossier opens, so the ~15s assembly is unchanged.
    Verified live: a GDELT event recovered
    *"Chinese Companies Used Crypto Exchange to Launder Iran's Black-Market Oil
    Sales"* (The Epoch Times) with a description and actors.
  - **Article-identity clustering (found while building the above).** GDELT codes
    **one row per actor dyad**, so a SINGLE article becomes many events — one
    produced **37**. Measured: **62.7% of events shared an article URL**. The
    signature gate (below) correctly stopped unrelated stories fusing, but left
    this fragmentation. Since two records citing the same article ARE the same
    story, `shouldCluster` and `dedupKeyFor` now treat a normalized article URL as
    definitive identity (scoped by event type, so one article read as both a
    `sanction` and a `trade` keeps both). Events in a 24h window **461 → 338**,
    and corroboration became real again (Seeking Alpha + Investing.com + CNBC on
    one story). 40 cluster/dedup tests.
  - **Readable titles** (`formatEventTitle`). GDELT's synthesized
    `ACTOR1 / ACTOR2 — City, Country` read as code fragments
    (`POLICE — Washington, District of Columbia, United States`). It is now
    restructured into a sentence — *"POLICE in Washington, District of Columbia,
    United States"* — from the same fields, inventing nothing. Applied in the
    dossier header and the live feed; a real headline passes through untouched,
    and a headline merely containing a "/" is not rewritten. 10 tests.
  - `article-meta.test.ts` (17 tests) covers entity decoding, attribute-order
    tolerance, body-meta rejection, bot-wall detection and suffix stripping.
  - Verified: 906 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Event dossiers, real headlines, and the clustering bug that
  was corrupting events. Includes a schema change (see the DB note below).
  - **Clustering was fusing unrelated stories.** A real event in the DB had 16
    "sources" including a bicycle-retailer article and a construction PR. Root
    cause: `shouldCluster` merged on `sameCountry && similarity >= 0.15`, and
    GDELT titles are synthesized as `ACTOR / ACTOR — City, Region, Country` — so
    every event from one city shared that tail and cleared the threshold for
    free. Three fixes: a new `clusterSignature` on the event contract (GDELT's
    GLOBALEVENTID, USGS's feature id) that forces merge-on-exact-match only; the
    location tail is stripped before tokenizing; the same-country floor moved to
    0.3. Measured on real data: **max sources 16 → 3**. `dedupKeyFor` now uses
    the signature too — without that, distinct signed events hashed identically
    and persisted as duplicates (22 of 473). Plus a `collapseDuplicateKeys`
    last-line-of-defence. 40 cluster/dedup tests.
  - **Real headlines** (`enrich.ts`). GDELT's bulk export carries no headline at
    all — only actor strings — which is why clicking a conflict showed a place
    name and nothing else. Events are now enriched from the ALREADY-ingested
    `NewsItem` corpus by normalized `host+path` key (raw URL matching recovered
    0/500; normalization recovers a real fraction). **202 of 461 events now have
    a genuine headline.** Never synthesized: an unmatched event says so.
  - **The dossier** (`event-panel.tsx`, rebuilt). Eight sections, each labelled
    with its own epistemic status: **What happened** (real headline/description,
    or an explicit "no headline available from this structured feed") · **Actors**
    (GDELT's Actor1/Actor2 with human-readable type codes — parsed and thrown
    away before) · **Where & when** (place, coordinates, and HOW precise:
    provider / named place / country centre) · **Detail** (per-type: magnitude,
    actor dyad, commodities) · **Observed** · **Why it matters** · **Potential
    exposure** · **Market reaction** · **Sources** · **Timeline** (source
    timestamps, earliest first). The header carries a corroboration badge
    (single source / corroborated / confirmed).
  - **Persisted details**: `headline`, `description`, `actors`, `providerCodes`,
    `placeName`, `geoMethod` columns on `GeopoliticalEvent`. `persistEvents` now
    backfills the row `id` onto the in-memory events — without it the state had
    no ids and the entity-links endpoint 404'd on every open.
  - Also fixed: `assembleState` with `refresh=1` returned stale cache instead of
    awaiting the rebuild, so the refresh button appeared to do nothing.
  - **Icon**: Investor Eye now uses `ScanEye` (sidebar, command palette, screen
    header, full-page map) instead of the generic `Earth`/`Globe`.
  - Verified: 840 tests pass, `tsc` + eslint clean, zero console errors in
    Chrome; dossier checked against live data.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Six capabilities: observed price reaction, event alerts,
  place-level geocoding, saved views, keyboard navigation, source health.
  - **Price reaction** (`lib/investor-eye/reaction.ts`, pure). Measures what the
    relevant instrument ACTUALLY did after an event — close-to-close returns at
    +1/+5/+20 sessions from real `Candles` rows, with the baseline date, the
    trading days of post-event history, and an explicit reason when it can't be
    measured. This is the observable counterpart to "potential exposure": the
    exposure block says what COULD matter, this says what the market did. Never
    predictive, never synthetic. `GET /api/investor-eye/reaction` +
    `ReactionPanel` in the event panel. Verified live: an 2026-09-11 Alaska
    quake returned `^GSPC +1=-0.483% +5=-0.535%`; events from today correctly
    return "not yet measurable" instead of a fake zero. 11 tests.
  - **Event alerts** (`lib/investor-eye/alert-rules.ts`, pure predicates).
    "Tell me when…" over the world feed: event types, severity floor, confidence
    /relevance floors, countries, commodities, keywords, and an optional
    lat/lon/radius fence. `matchRule()` returns the REASONS a rule fired (never
    a bare boolean), so an alert is always explainable. Persisted as
    `SystemConfig` JSON — no schema change — through a guarded
    POST/DELETE, with 5 preset rules. An empty rule refuses to match rather than
    firing on everything. `AlertsPanel` wired into the detail row. 22 tests.
  - **Place-level geocoding** (`lib/investor-eye/places.ts`, ~130 curated
    places). News-derived events only had a country, so they plotted at the
    COUNTRY CENTROID — "United States" pins landed in Kansas and made the map
    read as wrong. A curated gazetteer of financial centres, major ports,
    chokepoints (Hormuz/Suez/Malacca/Bab-el-Mandeb), and energy/industrial hubs
    now anchors the event where the headline says it happened; the country hint
    disambiguates, and matching is word-boundary so "china" never matches
    inside another word. Chokepoints are weighted highest because they drive the
    logistics story. 9 tests — which caught that `PA` and `PS` were missing from
    the country gazetteer, so Panama Canal / Gaza events had nowhere to plot;
    both added.
  - **Saved views** (`saved-views.tsx` + store): snapshot layers + window +
    projection + metric as a named posture ("Red Sea shipping watch") and
    restore in one click. Re-saving a name replaces it; restoring reconciles
    layer ids against the registry so a retired layer can't come back. View
    state only, never data.
  - **Keyboard navigation** (spec §34): `j`/`k` or ↓/↑ step through the
    newest-first event feed and open each one — the map is usable without a
    mouse. Ignored while typing or with a modifier held.
  - **Source health** (spec §15): `SourceHealthPanel` renders the real
    `SourceRun` accounting from `/api/investor-eye/health` — state, latency,
    last run, accepted/received — with a throttle shown as its own state, never
    folded into "error".
  - Verified: `npm run test` 816 passed, `tsc` + eslint clean, zero console
    errors in Chrome; reaction and alert APIs exercised against live data.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Removed the doubled close button on selection panels.
  `PanelShell` drew its own "×" while the Event/Country/Company panels already
  render one in their header, so the corner showed TWO overlapping crosses.
  `PanelShell` is now a pure frosted frame (documented as owning no dismiss
  affordance); the inline market card gained the close button it was relying on
  the shell for. Verified in Chrome: exactly one close button, still dismisses.
  no doc change — pure presentational fix, contracts unchanged.

- **Investor Eye** — Fixed the tooltip crash, added a loading state, and closed
  the dead gap in the analysis row.
  - **Crash on every map hover.** `tooltipFormatter` passed ECharts' own wrapper
    (`{name, value, severity, _datum}`) straight to `layer.tooltip()`, so
    `eventTooltip` read `undefined.eventType` — "Cannot read properties of
    undefined (reading 'eventType')". The click path already unwrapped `_datum`;
    the tooltip never did. Extracted `unwrapDatum()` (`map-echarts.ts`) and used
    it in both, plus a defensive guard in `eventTooltip` so a malformed datum
    degrades to a minimal tooltip instead of taking the map down. The bug was
    invisible to `tsc` (the payload is `unknown` at the ECharts boundary), so
    `map-echarts.test.ts` now drives the real formatter with wrapped payloads —
    8 tests, including the globe `[lon, lat]` altitude shape.
  - **Loading state.** The map now shows a centred dot-grid loader
    ("Loading world state · 24H window") over the canvas while the first
    world-state fetch is in flight, and the Live Event Stream shows its own
    loader. Previously the hero was simply blank for the ~15s cold assembly.
  - **Dead gap removed.** The analysis row was a 3-track grid, which reserves
    the height of its TALLEST child in every track — so the short
    "What Changed" column left ~300px of empty space. Replaced with CSS
    multi-column masonry (`lg:columns-3` + `break-inside-avoid`), so each panel
    packs directly under the previous one.
  - Verified in Chrome: hovering an event pin renders the tooltip, clicking it
    opens the Observed/tooltip detail panel, clicking a **conflict** pin works,
    zero console errors. `npm run test` 774 passed, `tsc` + eslint clean.
  docs updated: `docs/investor-eye-architecture.md`

- **Investor Eye** — Fixed the reported breakage (invisible globe, dead clicks,
  DATA UNAVAILABLE flapping, broken lower layout) and added conflict news.
  Diagnosed by loading the real page in Chrome, not by inspection:
  - **Globe was a blank sphere.** `echarts-gl`'s `globe` takes a raster
    `baseTexture`, not a `map`; the previous fix replaced the default bright
    texture with a 16×16 *solid dark* PNG — dark sphere on a dark page, so it
    read as floating dots. It now draws a real equirectangular world texture at
    runtime from the SAME GeoJSON the 2D map uses (`app-geo.worldGlobeTexture`:
    dark ocean `#0b1220`, lighter land `#2b3442`, cyan coastlines, graticule).
    Two bugs found while building it: `geometryRings` returned rings for a
    Polygon but polygons for a MultiPolygon (off by one nesting level, so
    nothing drew), and `scatter3D` reads a third coordinate as ALTITUDE — the
    2D-style `[lon, lat, value]` lifted pins into radiating spikes. 3D series
    now send exactly `[lon, lat]`.
  - **Clicking conflict/weather/energy pins did nothing.** `filterEventsLayer`
    (which builds all three category layers) set only a tooltip, never an
    `onClick`, so the category pins — the ones users click to ask "what is
    this?" — were inert. `buildTradeLayer` had the same gap. All now take an
    `onSelect` and `buildAllLayers` wires it.
  - **"DATA UNAVAILABLE" flapping.** `/api/investor-eye/state` awaited a cold
    assembly (~15–18s measured) even when a good previous state existed, and the
    client equated `data === null` with unavailable — including while the first
    fetch was still in flight. `assembleState` is now true stale-while-revalidate
    (fresh → stale + background rebuild → persisted last-known + rebuild → await
    only when there is genuinely nothing), labelled `CACHED` with a `refreshing`
    flag. The screen distinguishes LOADING / LAST KNOWN · REFRESHING /
    UNAVAILABLE. Confirmed in-browser: no flapping, banner reads
    "LAST KNOWN HH:MM UTC · REFRESHING".
  - **Lower layout rebuilt.** The selection panel used to render BELOW the fold,
    which is why a click appeared to "do nothing". The hero is now a map +
    360px right rail holding the selection panel and a new **Live Event Stream**
    (`live-feed.tsx`: time, type badge, severity dot, countries, source link,
    click-to-select, lens tabs with counts); "Explore the world" is gone. The
    map and rail share one bounded height so the rail no longer overflows.
  - **Conflict news.** Added five conflict-scoped wires (`gn-conflict-now`,
    `-mideast`, `-ukraine`, `-shipping`, `-coup`, tier 1, category `WAR`) so the
    Conflict lens is dense rather than relying on GDELT's CAMEO coding alone;
    the existing news adapter turns them into events unchanged.
  - 3 new tests (category-layer onClick wiring, trade-line selection, legend/
    registry consistency). Verified: `npm run test` 766 passed,
    `npx tsc --noEmit` clean, eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Full-page "map only" mode + a colour-coded layer system.
  - **Full-page mode** (`full-page-map.tsx`): an immersive presentation of the
    *same* surface — the world fills the viewport, with a top strip (identity,
    event/market counts, DATA UNAVAILABLE state, MAP/GLOBE, Esc-to-exit) and a
    bottom dock (colour-coded layer chips + time window + the selected event as a
    floating drawer). Reuses `MapLayer[]`, the store and `EventPanel`; it is a
    view, not a second screen. Portaled to `document.body`, page scroll locked,
    and `fullPage` is view state only — deliberately not persisted, so reopening
    never traps the user in full screen. Reachable from the header and from a
    "Map only" affordance on the map surface.
  - **Colour-coded tabs / layers**: `LAYER_META` now carries a group, accent
    colour, marker shape and one-line hint per layer, with a `LAYER_GROUPS`
    registry (Events · Hazards · Energy & Trade · Economy · Markets). The layer
    controller renders grouped, colour-coded chips plus a marker-shape legend;
    the timeline colours each time window by length and adds a severity rail
    legend. Point layers pass their registry symbol to ECharts, and
    `conflict`/`weather`/`energy`/`portfolio` are tinted by category instead of
    the old sign-based colouring — so categories no longer rely on colour alone
    (spec §8 / §34). `timeline.tsx` and the controller were rewritten.
  - 3 new registry tests; `.glass-card`/`-subtle`/`-drawer`/`-button` used
    throughout (no raw blur). Verified: `npm run test` 763 passed,
    `npx tsc --noEmit` clean, eslint clean.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Charts** — Fixed indices never rendering on charts (S&P 500, Dow, FTSE 100,
  Nifty 50, KSE 100, DAX and the rest). Four separate defects, all fixed:
  - **Wrong ticker.** The search registry registered indices under bare
    TradingView ids (`SPX`, `DJI`, `NDX`, `RUT`) and put those in the
    destination, but the data path only understands YAHOO tickers — Yahoo has no
    `SPX` instrument, so `/api/price-history` returned an empty series and the
    chart showed "Symbol not found". Added `src/lib/indices.ts`, a single index
    registry that maps both directions (`SPX` → `^GSPC`), and used it in
    `/api/price-history` and `/api/quote`. The palette's index entries are now
    GENERATED from it, so the two can never drift again.
  - **Chart ignored later symbol changes.** `ChartWidget` initialised its state
    from the `symbol` prop exactly once and never reconciled, so the chart tab
    (which passes only `symbol`) kept rendering whatever it first mounted with.
    Added a prop-sync effect, gated to the uncontrolled path so a controlled
    `state=` host keeps sole ownership.
  - **Dead source for PSX indices.** Yahoo delisted PSX (`^KSE100` 404s, as does
    `.PSX`/`.KA` for the index), and `INDEX_UNIVERSE.PK` was deliberately emptied
    — so KSE-100 had no data at all. Added `fetchers/psx-index.ts`, which reads
    the exchange's own `dps.psx.com.pk/historical` endpoint (true OHLC, one
    request per month, parallel) for KSE-100/30 and KMI-30, plus the `eod`
    endpoint for their live quote so the chart footer is populated.
  - **Palette ordering.** The command palette grouped results by entity kind, and
    `security` (JDDS ETFs) + `instrument` (indices) are both labelled
    "Instruments" — so the grouping split them into two same-named sections and
    re-sorted the second one, burying a top-scoring index under ETFs that merely
    matched the same words. Both now share one section key and keep the
    resolver's score order.
  - Indices also carry their own currency now (`^FTSE` charts in GBP, `^NSEI` in
    INR), instead of inheriting the caller's default. Verified in-browser: each
    of S&P 500 / Dow / FTSE / Nifty / KSE 100 / Nikkei / DAX loads real bars and
    paints a candlestick chart with no console errors. 22 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **Investor Eye** — **Phase 4: made the feed actually useful, map-first layout,
  3D globe.** The previous pass was a correct pipeline pointed at a nearly empty
  input — 146 events, all USGS earthquakes, zero from GDELT — so the map showed
  an earthquake feed while ~1,000 news items/day sat unused in JDDS.
  - **GDELT was completely broken and is now fixed.** Root cause found by
    measurement, not assumption: the DOC API took >13s per request (the shared
    `safeGet` transport hard-caps at 10s) *and* returned 429 on short bursts, so
    it produced **zero** events every run. Replaced with GDELT's **bulk 15-minute
    Event export** (`data.gdeltproject.org`): ~120 KB, **2.2s**, not rate-limited,
    and far richer — CAMEO codes, actor names/countries, Goldstein scores,
    mention counts and exact action coordinates. Uses Node's built-in `zlib` (no
    new dependency) and reads the ZIP central directory because GDELT sets the
    data-descriptor flag. The DOC API is retained only as a best-effort fallback.
    Result: **1,790 raw events → 400 after relevance filtering, 2.2s.**
  - **`safeGet` gained an opt-in `binary: true`** so binary payloads survive the
    transport (its default UTF-8 decode replaces invalid bytes with U+FFFD and
    irreversibly corrupts a zip). Also fixed: `lastupdate.txt` advertises `http://`
    URLs that the https-only transport (correctly) refuses; the scheme is now
    upgraded rather than weakening security.
  - **New `cameo.ts`** decodes CAMEO root codes to event types, the Goldstein
    scale to severity, and — critically — **FIPS 10-4 to ISO2**. GDELT's action
    country is FIPS, which *conflicts* with ISO for important countries (FIPS
    `AS`=Australia, `CH`=China, `SZ`=Switzerland, `UK`=UK); using the codes
    directly would have placed events in the wrong countries.
  - **New `relevance.ts`** scores investor relevance from GDELT's structured
    fields (material conflict, economic type/channel, state-to-state dyad,
    actor type, Goldstein, reach) so the firehose becomes a feed. GDELT codes
    everything — local crime, sport, university meetings — and without this the
    map was noise ("POLICE / Arizona"). Now a typical file yields Ukraine/Russia
    military, US–Iran, Arab League, sanctions and trade events instead.
  - **New news-to-events source (`sources/news.ts`)**: converts the already-ingested
    `NewsItem` rows into events — no new feed, no credentials, ~0.3s. **571 rows
    to 158 real events** covering the Fed, oil, NATO/Russia, Ukraine refinery
    strikes, Saudi–Houthi and India trade deals. `relevance` + `relevanceReasons`
    are persisted and the feed is ranked by relevance.
  - **Fixed a pre-existing bug that made `Candles` permanently empty.** The
    Python bridge emits `date`, but `updateCandleCache` read `ts`, so every bar
    was stamped `new Date()` and the composite-key upsert collapsed 955 bars to
    11 rows. It now reads the real date and skips undated bars. With the new
    `history.ts` backfill (reusing that existing path), **^GSPC now has 131 real
    daily bars, BTC-USD 187, CL=F 131** (2026-03-16 to 2026-09-16), so historical
    analogues finally have real series. The backfill is fire-and-forget: awaiting
    30 markets took ~170s and blocked the first world-state response, which is
    why the map initially rendered "0 events".
  - **Layout is now map-first**: the world is a full-width hero (~55vh, 82% of
    viewport width) with the layer/timeline controls directly beneath, and every
    detail panel (selection, What Changed, risk, transmission, portfolio, graph)
    stacked below the fold so nothing squeezes the map.
  - **3D globe**: a MAP/GLOBE toggle lazy-loads `echarts-gl@2.1` (new dependency,
    justified: it is the maintained ECharts globe). Globe mode uses `scatter3D`/
    `lines3D` — plain `scatter` with `coordinateSystem: 'globe'` silently fell
    back to index positioning and clumped pins in a corner — and a generated
    inline dark PNG texture, because echarts-gl's globe has **no `map` property**
    and its default bright texture rendered a white sphere that hid the data.
    Any globe failure (chunk, WebGL) falls back to the flat map automatically.
  - New routes: `GET/POST /api/investor-eye/history`.
    docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
    `docs/CHANGELOG.md`

- **Charts / Market Bubbles** — Rebuilt Market Bubbles on the same real JDDS data
  the Command Center heatmap uses, and made it an actual volume-measuring tool.
  The old screen pulled `/api/stocks` (max 100 assets) and, for ANY equity market
  that returned nothing, silently substituted a hardcoded 8-symbol **Pakistani**
  demo list — so most markets rendered invented data, which is what made it look
  random. It now reads `/api/heatmap`, drops all demo/seed constants, and offers
  every one of the 31 `HEATMAP_MARKETS` instead of a hardcoded country list.
  - **Honest unit handling.** `Price.volume` is quote-currency notional for crypto
    but a share count for equities, so summing it mixes units and multiplying it
    by price double-counts. Added `turnoverFor` / `isNotionalVolume` in
    `src/lib/heatmap.ts` to normalise both into **turnover** (traded value in the
    market's currency) — the metric bubbles and the panel now size by default.
  - **New Volume Analytics panel** (`src/components/screens/volume-analytics.tsx`):
    traded value, instrument coverage, mean/median/largest, top-10 share, an HHI
    concentration read, contribution bands, and ranked top contributors. Computed
    server-side by `summarizeVolume()` over EVERY priced instrument in the market
    (not just the ≤220 tiles) via the new opt-in `GET /api/heatmap?volume=1`, which
    adds `HeatmapPayload.volume: VolumeSummary`.
  - Verified live: CRYPTO 1,385/1,455 instruments, $187.4B turnover, HHI 2553
    ("highly concentrated"); US 6,314 instruments. 16 unit tests pin the unit
    semantics, banding, concentration and top-N truncation.
  docs updated: `docs/ARCHITECTURE.md` (volume-unit contract), `docs/NAVIGATION.md`
  (route/task rows), `docs/OVERVIEW.md`, `README.md`

- **Investor Eye** — Completed Phase 2 (spec §63). Closed four real gaps left by
  the previous pass and fixed three defects found while verifying in-browser:
  - **2.8 Market transmission** was computed and served but never rendered —
    added `TransmissionsPanel`, which draws each `Event → country → channel →
    asset` chain and labels every hop `OBSERVED`/`INFERRED`, so an inference is
    not read as a fact.
  - **2.9 Historical analogues** had an API with no caller — added
    `AnaloguesPanel` (inside the event panel) rendering real stored series,
    sample size, date range, and an honest `UNAVAILABLE` when history is
    missing, plus the non-prediction disclaimer verbatim.
  - **2.10 Relationship graph** was missing entirely — added the additive
    `Relationship` model (and `EventEntity` / `Country` rows are now actually
    written during ingestion), a pure `graph.ts` builder (per-kind caps, honest
    truncation, strongest-class preservation), `graph-data.ts` (edge derivation:
    event co-mention and stored attributes → `OBSERVED`),
    `GET /api/investor-eye/graph`, and a `GraphPanel` ECharts force layout whose
    edge colour and tooltips encode `relationClass`. Relational, not a graph DB
    (ADR-011).
  - **2.11 AI Analyst** was missing — added seven read-only agent tools
    (`src/lib/agent/investor-eye-tools.ts`, spread into `TOOLS`) plus a `world`
    research agent, so the model answers from structured data with provenance
    and never on the query path.
  - **Fixed:** the assembled-state cache was module-level, and Next evaluates
    each route in its own module instance, so `/state`, `/risk`, `/markets` and
    `/layers` each cold-ran the full GDELT/USGS ingestion — `/risk?hours=24`
    took 20–100s. The cache and its in-flight guard are now `globalThis`-anchored
    and keyed by window, so a route fan-out triggers one ingestion per window
    (measured ~6s once warm).
  - **Fixed:** company pins on the map were dead — they now open a
    `CompanyPanel` with profile + derived relationships.
  - **Fixed:** panel selection was not exclusive, so clicking an event from the
    country panel never rendered (the stale panel kept priority).
  - 42 new tests (relationship-graph builder, cache semantics, agent tools).
    docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
    `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Search** — Fixed a broken pre-existing working-tree change in
  `global-search.tsx`: `pinnedCommands` was removed but its render block
  remained, so the file did not typecheck (`tsc` reported a dangling reference).
  Removed the orphaned block, preserving the surrounding WIP intent.
  no doc change — restores a file to a compiling state; no contract changed.

## 2026-09-15

- **Search** — The palette's bottom group is now simply the app's 11 top-level
  tabs in sidebar order (ChatBot → Price Alerts, including Investor Eye), not a
  32-item sub-page dump. Removed the inline calculator, parameterized command
  rows, and their wiring (`calc.ts`, `commands.ts`, quick-alert and watchlist
  side effects). Typing still searches instruments, indicators, markets and
  actions via the resolver, so this only changed the pinned list.
  no doc change — palette presentation only; resolver/search contracts unchanged.
- **Investor Eye** — New **Investor Eye** world-state surface (Phase 1 + 2): a
  large interactive ECharts world map with a pluggable `MapLayer` system
  (events, markets, conflict, energy, trade, weather, economy, companies,
  portfolio, risk), a timeline (1H–30D), layer controller, country/event
  intelligence panels, "What Changed" summary, and honest data-freshness
  indicators. Backed by a new **additive** event tier `src/lib/investor-eye/`:
  `EventSource` adapters (GDELT DOC 2.0 + USGS, both free/keyless, fetched
  through the existing `connectors/security.safeGet`), pure normalization
  (classification, clustering/dedup, internal data-quality confidence, grid
  aggregation), a real country gazetteer, server SWR cache + persisted
  last-known, an in-process ingestion cron, and 13 `/api/investor-eye/*` routes
  (state, events, countries, markets, layers, economy, companies, portfolio,
  risk, analogues, query, health). Markets reuse the existing `IndexQuote` +
  yfinance path and portfolio exposure reuses `use-portfolio-engine` — no second
  market/portfolio/news stack. Phase 2 analytics are deterministic (risk
  decomposition, exposure, `OBSERVED|HISTORICAL|INFERRED` transmissions,
  historical analogues, keyword+gazetteer NL map search — no LLM on the query
  path). New JDDS models `Country`, `GeopoliticalEvent`, `EventEntity`,
  `SourceRun`; vendored `public/geo/world.geo.json` (Natural Earth, via
  `scripts/fetch-world-geo.mjs`); new `investor-eye` sidebar tab registered in
  sidebar config, search registry, top-bar and the shell. A failed source is
  `UNAVAILABLE`, never a fake zero. 106 new tests.
  docs updated: `docs/investor-eye-architecture.md` (new), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/DATA-FLOW.md`, `docs/DECISIONS.md`,
  `skills/ARCHITECT.md`
- **Build** — `scripts/doctor.js` now detects **schema drift** on an existing
  `jdds.db` and self-heals with `prisma db push`. Previously it only pushed when
  the DB file was *missing*, so an install carrying the old committed seed would
  never receive models added since (the connector + Investor Eye tables) and
  would 500 on every query against a missing table. Expected table names are
  parsed from `schema.prisma`, so the check cannot itself go stale; a locked or
  corrupt DB is left to the existing integrity guard.
  no doc change — self-healing boot fix; no documented contract changed.

- **Screener** — Fixed the broken glyphs on the Market Screener (the `□` boxes
  in the "Global Markets Overview" row and in the table headers). Root cause was
  a pre-existing encoding corruption, not a missing icon: commit `34d76fd`
  (frosted-glass pass) re-encoded `market-overview.tsx` and turned 80 non-ASCII
  characters — em dashes, middots, ellipses, en dashes — into `U+FFFD`
  replacement characters baked into the source. Recovered the original
  characters by matching each damaged line's ASCII skeleton against the last
  clean revision (`c8ec9d3`) and restored them; also fixed one instance in
  `src/app/globals.css`. Verified zero `U+FFFD` remains across all source files.
  no doc change — character-encoding repair, no contract or architecture change.

- **Connectors/UI** — De-duplicated and expanded the provider surface. The AI
  Agent screen previously showed a generic "Provider" **dropdown and** a
  provider **list** — the same choice twice, and the list's "Set up" button
  navigated back to the screen you were already on. It is now a single
  preset-grid picker: click a provider and it fills the base URL + model, leaving
  only the key. Added `src/lib/agent/presets.ts` with **14 working
  OpenAI-compatible presets** (OpenAI, Anthropic, Ollama, LM Studio, Groq,
  DeepSeek, Mistral, Google Gemini, xAI, OpenRouter, Together, Perplexity,
  Fireworks, Custom), and the catalog's AI entries are now **derived from that
  list** so a new preset appears in both places with one edit. Also fixed a real
  bug: `setLLMConfig` rejected any provider without a key, so **keyless local
  servers (Ollama/LM Studio) could not be saved** — it now allows local base URLs
  (`isLocalBaseUrl`) and stubs `"local"` since some clients require a non-empty
  string. Added 12 market/crypto providers (Finnhub, Polygon, Alpha Vantage,
  Twelve Data, Marketstack, CoinGecko, CoinMarketCap, Kraken, …) — **72 providers
  total**, up from 53. Env-var key status is now a single list
  (`CATALOG_ENV_VARS`) shared by `/api/providers` and `/api/settings`, so the two
  cannot disagree. 21 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Moved the provider catalog OUT of Data Sources and into
  the settings section that actually configures each provider, so APIs are no
  longer dumped in one place: **AI Agent** shows AI & LLM, **Market Data** shows
  Market Data + Crypto, **Integrations** shows all 44 Economics & Macro sources,
  and **Data Sources** now shows only "Your own data" (the wizard). The new
  `provider-list.tsx` renders a catalog slice in context with a module-level
  fetch cache, so appearing in four sections still costs one request. The
  Integrations section also dropped its hand-written rows (which listed
  `finnhub`/`binance`/`coingecko` — nothing consumes those) in favour of the
  derived list, leaving only AI Model + Database as genuine status rows.
  Long lists (economics) are collapsible with a filter box. 543 tests pass.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Added a browsable **provider catalog** to Settings → Data
  Sources, grouped by what each provider is for (AI & LLM, Economics & Macro,
  Market Data, Crypto, Your own data) instead of a flat connector list —
  53 providers across 5 collapsible categories with per-category counts.
  `src/lib/connectors/catalog.ts` builds it purely (`buildCatalog(env)`), and
  **Economics entries are derived from `ECON_SOURCES`**, so the catalog cannot
  drift from the fetch layer. Status is honest: `builtin`, `connected`,
  `not_configured`, or `available`, computed from the real environment — of 44
  economics sources only FRED is key-gated, and it shows `needs FRED_API_KEY`
  until set. Buttons never claim to have saved a key: built-ins show a status
  pill, Custom REST opens the wizard, and env-gated providers route to
  Settings → AI Agent / Integrations (via the destination bus, since Settings is
  a modal, not a tab). New `GET /api/providers`. 10 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **UI** — Navigation icon and label pass. Renamed the **Market Workspace** tab
  to **Chart Workspace** (tab id and `src/lib/market-workspace/` folder unchanged)
  so the label says what the screen is, and gave it the candlestick icon that the
  screener was using. The screener now uses `ScanSearch` (magnifier over scan
  lines) to read as "screen the market" instead of duplicating the chart glyph,
  and Portfolio switched from `Briefcase` to `ChartPie` per request. Applied the
  same choices to every surface that carried a stale icon: sidebar config, the
  search registry (`page-market-workspace`, `page-screener`, `page-portfolio`,
  the screener sub-pages, and the three open actions), the palette's `NAME_ICON`
  map, and both page headers (Chart Workspace had no icon at all; Portfolio and
  Screener used the old glyphs). All `open …` action labels and the page title
  updated too; old labels kept as search aliases so muscle memory still resolves.
  docs updated: `docs/OVERVIEW.md`, `docs/GLOSSARY.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`, `skills/REMEMBER.md`

- **Search** — Tests + docs for sub-page navigation. Added
  `search/subroute.test.ts` (channel semantics: tab scoping, focus pass-through,
  seq re-fire, scoped clear) and registry assertions that sub-pages carry a
  `subroute`, nest under their parent `group`, and that only children are marked
  `child`. Documented the subroute channel and its two invariants in
  `docs/ARCHITECTURE.md`, and the "add a palette sub-page" recipe in
  `docs/NAVIGATION.md`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Sub-page navigation: `Destination.subroute` (previously emitted by
  the registry but ignored by the shell) is now honored. Added a `pendingSubroute`
  channel + `useSubroute(tab, handler)` hook so keep-alive screens react to
  `economics.calendar`, `journal.<tab>`, `discovery.<tab>`, `alerts.<view>`, and
  `settings.<section>`; the shell also routes `tab:'settings'` to the Settings
  modal (it previously switched to a tab that rendered nothing). Registered ~40
  sub-pages in the registry (grouped under their parent, rendered indented in the
  palette's "Go to"), added an Economics "Calendar" section with indicator focus
  highlighting, and removed the superseded `search/settings.ts`. New:
  `src/hooks/use-subroute.ts`, `getPageEntries()`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Charts** — Drawing toolbar rendered the same `MousePointer2` glyph for every
  tool, so the Lines/Shapes/Analysis grids were unreadable at a glance. Added a
  `TOOL_ICON` name→lucide map in `chart-widget.tsx` (unknown names fall back to
  the pointer, so a future tool never renders blank) and wired each button to its
  own glyph, with the active tool tinted `primary` for contrast. Also split the
  two colliding registry icons: `ray` now uses `move-diagonal` and `arrow` keeps
  `arrow-up-right`.
  no doc change — UI-only change, drawing contracts and tool registry shape unchanged.

- **Connectors** — Hardening pass on the custom REST connector after review.
  Fixed a silent URL bug: `new URL(path, base)` treats a leading `/` as
  root-relative, so a base like `https://api.example.com/v1` + `/quote`
  produced `…/quote` and **dropped the `/v1` prefix** — a very common API shape
  that would have 404'd with no explanation. Added `joinPaths()`, which joins
  the base pathname explicitly, and preserved any query string the operator put
  on the base URL (a common spot for a query-param key). Added `validateHeaders`
  so CRLF injection / empty header names fail with a clear config error instead
  of Node's opaque `ERR_INVALID_CHAR`. Anchored the connector registry on
  `globalThis` (same reason `lib/db.ts` anchors Prisma) so dev HMR cannot leave
  a second empty registry behind. Verified end-to-end against the live Binance
  API with a `/api/v3` base: multi-symbol pulls, records, and agent reads all
  correct. 9 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors** — Completed the connector loop end-to-end. Fixed a dishonest
  count: `ingestRecords` always returned `rejected: 0` even when `mapResponse`
  silently dropped rows, so an import could report success while losing records.
  Mapping now reports `extracted` / `rejectedRequired` / `rejectedIdentity` /
  `deduped` (`mapResponseDetailed` in `mapping.ts`) and every extracted row is
  accounted for. The Data Sources panel gained a **Datasets** browser with
  **Pull** (fetch through the connector and ingest), per-dataset parameter
  inputs, a records table showing provenance, delete-dataset, and a **Sample
  test value** field in the wizard (draft tests previously failed with "Missing
  required parameter" because no value was ever supplied). Pull errors now
  return 400 with the real message for a misconfigured connector instead of an
  opaque 502; connector fetch errors are classified (`invalid_config` /
  `blocked` / `timeout` / `too_large`) rather than all reported as `network`.
  New `DELETE /api/datasets?id=…`. 6 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`

- **Agent** — The research agent can now read operator-connected datasets via
  three read-only tools (`src/lib/agent/dataset-tools.ts`): `list_datasets`,
  `describe_dataset`, `query_dataset`. They are spread into `TOOLS`, so the
  existing tool loop picks them up with no loop change; the fundamentals and
  risk agent prompts were updated to use them. Every tool result states
  provenance (`CUSTOM` vs. canonical scraper data) so the LLM never invents a
  source. Added `queryRecords` / `datasetSummaries` / `findDatasetByName` to
  `connectors/store.ts`; filters are exact-match on mapped field names
  (case-insensitive), JS-evaluated because SQLite cannot query inside the JSON
  `values` column. 15 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Connectors** — Introduced the Universal Data Connector Layer
  (`src/lib/connectors/`): a capability-addressed connector tier that sits
  *after* the existing scraper chain and before route-level demo fallbacks.
  Added hardened outbound security (`security.ts`: canonical IP
  classification, DNS validation + pinned lookup, `redirect: manual`, streamed
  5 MB cap, ≤10s timeout), AES-256-GCM credential encryption (`secrets.ts`,
  local auto-generated key vs. `CONNECTOR_SECRET_KEY` on hosted), a declarative
  `custom-rest.ts` connector (GET + percent-encoded `{{param}}` substitution),
  mapping/`recordPath`/`recordKey` dedup (`mapping.ts`), the crypto fetcher
  migrated as the Phase-2 proof (`providers/crypto.ts`, legacy facade retained),
  and server-side capability resolution (`GET /api/data/[capability]`).
  New JDDS models: `DataConnector`, `CustomDataset`, `CustomDatasetField`,
  `CustomDatasetRecord`, `ConnectorMapping` — custom data never writes to
  `Asset`/`Price`/`Candles`. New routes: `api/data-sources`,
  `api/data-sources/test`, `api/datasets`. DataHub gained an optional
  provenance envelope + `CUSTOM` tag and a `capabilityTopic` helper (no internal
  redesign). New Settings → Data Sources wizard (`data-sources-panel.tsx`).
  Deferred: webhooks, POST bodies, pagination, OAuth, `~` dataset search, agent
  `query_dataset`, AI connector generation.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`, `README.md`

- **Search** — The palette is now full navigation, not just search. The bottom
  group is generated from `getAllPages()` so every registered page is reachable
  (adding a `registerPage` entry adds a nav row automatically); it is labeled
  "Go to", collapsible, and part of the keyboard list. Added paging keys
  (PageUp/PageDown/Home/End), a conditional bottom scroll-fade so overflow is
  visible, and a `nameIcon` map for registry string icon names.
  docs updated: `docs/ARCHITECTURE.md`
- **Aurora** — Made the shipped bearish color a proper pure red (`#ff0000` core /
  `#3a0000` edge) instead of the yellowish `#ff3e3e`, so the default Eclipse
  preset's red no longer reads orange.
  no doc change — default color values only; palette model/contract unchanged.
- **Search** — Wired the command palette's cross-tab pivots and parameterized
  commands to real behavior (they were previously cosmetic). `alert SYMBOL` now
  creates a ±3% CHANGE_PCT watch via new `lib/alerts/quick-alert.ts` and opens
  the Alerts tab; `watch SYMBOL` calls new `addToWatchlist` /
  `removeFromWatchlist` / `isInWatchlist` exports in
  `lib/dashboard/watchlist-store.ts`; `chart SYMBOL` opens the chart. The
  misleading `compare` verb was removed, registry actions gained `requiresArg`
  so they never render as bare commands, failures surface an inline error
  instead of a fake recent, and the keep-alive Alerts screen re-lists on a
  `be:alerts-changed` event. `MarketNews` gained a `symbol` prop (seeds the
  `ticker:` operator); `MarketOverviewScreen` gained `initialSymbol`; the
  destination bus in `stock-chat.tsx` now routes `tab:news`/`tab:discovery`
  symbols.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Docs** — Documentation/skills audit before sharing with an external tool.
  The `docs/` set was already current; the agent *skills* had drifted badly and
  were corrected against code: `skills/ARCHITECT.md` §2–4 described a pre-JDDS app
  ("no database", "only `/api/news`", 6 tabs, SQLite listed as PLANNED) — rewritten
  to the JDDS/scheduler/agent reality; `skills/REMEMBER.md` (DB, tabs, agent,
  retired `src/lib/customize/`) and `skills/GOALS.md` (agentic research now
  active, not deferred) updated; `skills/README.md` skill list fixed (6 → 8);
  `CONTRIBUTING.md` "no database/demo data" claim corrected.
  docs updated: `docs/DECISIONS.md` (mirror), `docs/CHANGELOG.md`
- **Search** — Completed the command-center improvement phases. Phase 4:
  deterministic synonym/acronym expansion (`expandTerms`), visit-history
  personalized ranking, and cross-tab `related` pivots for a resolved
  instrument. Phase 5: offline in-palette calculator + indicative currency
  conversion (`calc.ts`) and parameterized commands with argument autocomplete
  (`commands.ts`). Phase 6: ARIA combobox/listbox semantics with a polite live
  region, memoized rows, and a mobile-sized palette. New store state: `visits`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Result UX pass on the command palette: groups now show per-kind
  counts and collapse on click, results can be pinned (persisted to
  `localStorage` and replayed from a serialized destination) or have their symbol
  copied, the footer shows "N of M results", and a zero-hit query offers a
  "did you mean" correction from the static registry (`suggestCorrection`).
  `ResolvedSearch` gained `total` + `suggestion`.
  docs updated: `docs/ARCHITECTURE.md`
- **Search** — Added a query grammar to the command center: scoped prefixes
  (`>` commands, `#` instruments, `@` indicators, `/` pages, `~` your data, `?`
  syntax help) and field operators (`kind:`, `class:`, `market:`, `symbol:`).
  `resolver.ts` now parses scope/filters before resolving, and the palette shows
  a scope chip, a syntax help card, a clear button, and scope-aware empty states.
  The header trigger gained a contextual per-tab placeholder, a platform-aware
  ⌘/Ctrl shortcut label, and a live index count.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **Market Workspace** — Interactive drag placement now keeps a panel where it was
  dropped: added `placePanel` (absolute placement, pushes displaced panels down),
  `clampPanels` (bounds-only, row-preserving) and `packPanels` (full repack for
  templates/repair); `normalizePanels` is deprecated as an alias. Added
  `recomputeRows` so the grid ends at its content height instead of scrolling
  into empty space. New charts seed from the layout's lead instrument instead of
  hard-coded AAPL, and panels gained a `chrome: 'minimal'` full-page mode.
  Duplicate/remove moved into the panel menu (copy/trash icons).
  no doc change — no documented shape changed; `/lib/market-workspace/` is
  already mapped in `docs/NAVIGATION.md`.
- **Command Center** — New layouts can start from a persona preset:
  `MarketView` gained `templateId` (threaded `market-views.tsx` →
  `dashboard-screen.tsx`), and the new-layout flow was extracted into
  `new-layout-dialog.tsx`.
  no doc change — additive field; dashboard/workspace contract unchanged.
- **UI** — Added a `variant` prop to the shared `TabBar` (`glass` default,
  `subtle` for the new `.tab-bar-subtle` control-strip tier), applied to the
  Command Center market tabs.
  docs updated: `docs/ARCHITECTURE.md`, `.opencode/skills/black-eclipse-ui/SKILL.md`
- **Heatmap** — Tile sizes are compressed before grouping (sqrt for crypto,
  ^0.75 for equities) so a mega-cap no longer flattens the board; added
  `rawMarketCap` so tooltips and sector totals keep showing the true figure.
  no doc change — additive field on an internal heatmap shape.
- **Aurora** — `normalizePalette` now validates every color is real hex (guards
  the shader against malformed values); `setPalette` normalizes + clones so
  applying a preset never stores a shared module reference. Presets refactored
  through a compact `preset()` helper, swatches render a bearish→bullish ramp,
  and `theme.test.ts` covers every preset.
  no doc change — internal hardening, contract unchanged.
- **Docs** — Made the documentation obligation enforceable: every change must now
  append a `docs/CHANGELOG.md` entry (including changes needing no doc update),
  and an always-on rule was added in `AGENTS.md` so it applies to every session
  rather than only doc-keyed tasks.
  docs updated: `docs/CHANGELOG.md`, `docs/README.md`, `skills/DOCS.md`,
  `skills/REVIEW.md`, `.opencode/skills/black-eclipse-docs/SKILL.md`, `AGENTS.md`
- **Docs** — Established the documentation system: a flat canonical doc set in
  `docs/` plus an always-on obligation in `AGENTS.md`, the `black-eclipse-docs`
  skill, `skills/DOCS.md`, and the Documentation Review section in
  `skills/REVIEW.md`. Added a maintained change log (this file).
  docs updated: `docs/README.md`, `docs/OVERVIEW.md`, `docs/QUICKSTART.md`,
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, `docs/GLOSSARY.md`, `docs/CHANGELOG.md`
- **Docs** — Corrected a pre-existing drift: `black-eclipse-workspace` skill and
  the new docs described a paper broker (`dashboard/paper-broker.ts`,
  `trading-widgets.tsx`, `broker/types.ts`) that does not exist. Trading widgets
  are `UNAVAILABLE` stubs in `src/lib/dashboard/registry.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/GLOSSARY.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`
