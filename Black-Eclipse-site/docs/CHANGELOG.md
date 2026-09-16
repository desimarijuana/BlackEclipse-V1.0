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

## 2026-09-16

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
