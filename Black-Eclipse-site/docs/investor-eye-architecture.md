---
title: Investor Eye — Architecture & Audit
status: Current
last-verified: 2026-09-16
---

# Investor Eye — Architecture & Audit

**Who this is for:** anyone implementing or extending Investor Eye (the
financial/geopolitical world-state surface). Read §1–2 for the audit, §3 for the
design, §4 for the Phase 1 build order, §5 for Phase 2, and §5b–5d for the
later presentation/quality passes (globe, colour-coded layers, full-page mode,
and the runtime bugs fixed after them).

> This document is Phase 0's output. The repository is authoritative: where the
> implementation spec and the code disagreed, the code won and this record notes
> the adaptation.

---

## 1. What already exists (Phase 0 audit)

BlackEclipse is a **single-page Next.js 15 + TypeScript SPA** backed by **JDDS =
SQLite (`jdds.db`) via Prisma** (`better-sqlite3` adapter). There is **no URL
router for screens** — navigation is an `activeTab` state machine in the shell,
with sidebar tabs, keep-alive mounts, plus a command palette. The audit below
maps the spec's assumed subsystems onto what is actually present.

### 1.1 Relevant existing systems

| Subsystem | Where | Relevance to Investor Eye |
|---|---|---|
| App shell / tab state | `src/components/screens/stock-chat.tsx` | New screen must be a `visited`-gated keep-alive tab, `next/dynamic(ssr:false)` chunk. |
| Tab registry | `src/components/layout/sidebar.tsx` (`AppTab`), `src/lib/sidebar/config.ts` | Add a tab id + nav definition; reconcile logic auto-appends new ids. |
| Command palette | `src/lib/search/registry.ts` (+ `types.ts`, `grammar.ts`, `resolver.ts`), `global-search.tsx` | Register a page entity so `/`-scope and "Go to" reach it. |
| Client data layer | `src/lib/workspace/data-hub.ts` | Reusable pub/sub with TTL, provenance envelope (`LIVE\|CACHED\|HISTORICAL\|DEMO\|ESTIMATED\|CUSTOM\|UNAVAILABLE`). Use topics, don't hand-roll fetch. |
| Client UI state | Zustand stores (`src/lib/*/store.ts`) | Investor Eye state (selected country/event, layers, time range) should be a Zustand store, localStorage-persisted. |
| JDDS schema | `prisma/schema.prisma` (37 models) | Add only the models that don't exist (see §1.3). |
| Mutation guard | `src/lib/api-guard.ts` (`guardMutation`, `guardExpensiveMutation`, `rateLimit`) | Ingestion/refresh POSTs must be guarded. |
| Outbound security | `src/lib/connectors/security.ts` (`safeGet`) | **Reuse** for all outbound source fetches (https-only, DNS-pinned, size-capped, no redirects). |
| Background workers | `src/instrumentation.ts` + `src/lib/scraper/scheduler.ts`, `src/lib/connectors/refresh-scheduler.ts` | Add an ingestion cron following the same mutex/boot-grace/yield discipline. |
| Server cache | in-route SWR memory caches (e.g. `api/indices`, `api/economics/snapshot`), `SystemConfig` JSON persistence, `MacroSeries` | Cache expensive source pulls; no Redis needed. |
| Design system | `.glass-card*`, `.glass-drawer`, `.glass-button`, `TabBar` | All panels/tiles/toolbars must use these. |
| ECharts | `echarts@^6.1.0` already a dependency; used in chart, journal, economics, heatmap | Reuse — no new chart dependency; map is `echarts` geo. |

### 1.2 Existing reusable components & helpers

- `cn()` (`src/lib/utils.ts`), `TooltipProvider` + `TabBar` UI primitives.
- **DataHub** `registerTopic` / `useTopic` / `jsonTopic` / `capabilityTopic` — the
  correct client data path; provenance is explicit.
- `prisma` + `yieldToEventLoop()` (`src/lib/db.ts`) — synchronous-write
  discipline is mandatory for bulk ingestion.
- `getConfigJSON` / `setConfigJSON` (`src/lib/settings.ts`) — JDDS key/value
  cache (already used for feed health, persisted payloads).
- `toMarketId` / `marketDisplayName` / `currencyFor` (`src/lib/markets.ts`) —
  single source of truth for market ids/names/currencies.
- `useSubroute` (`src/hooks/use-subroute.ts`) — for palette sub-routes.

### 1.3 Existing database models (do not duplicate)

Market universe: `Market`, `Asset`, `Price`, `IndexQuote`, `Candles`.
News: `NewsItem`, `SourceHealth`. Macro: `MacroSeries`.
Scheduling/config: `CronJob`, `SystemConfig`.
Agent memory: `ResearchReport`, `AgentRun`, `ResearchFinding`.
Alerts: `PriceAlert`, `PriceAlertEvent`. Journal: ~20 models.
Connectors: `DataConnector`, `CustomDataset`, `CustomDatasetField`,
`CustomDatasetRecord`, `ConnectorMapping`.

**There is no** `Country`, geopolitical `Event`, `EventEntity`, `Relationship`,
`RiskObservation`, or connector-run-log model. `Asset.country` and `Market.country`
are plain strings, not entities.

### 1.4 Existing APIs

`stocks`, `quote`, `price-history`, `asset-details`, `symbols`, `markets(+global)`,
`indices`, `forex`, `commodities`, `heatmap`, `news(+status,alert)`,
`economics(+snapshot,calendar)`, `search(+global,index)`, `agent(+chat,research,
activity)`, `journal/*`, `alerts/*`, `scraper(+import)`, `refresh`, `settings`,
`cron(+run,refresh-news)`, `data-sources(+test)`, `datasets`, `data/[capability]`,
`providers`.

**Reuse, don't duplicate:** market observations come from `/api/indices` (which
already persists `IndexQuote` and a full payload in `SystemConfig`); economic
observations come from `/api/economics/snapshot` + `lib/economics/`.

### 1.5 Existing data sources

- **Market:** yfinance bridge / TradingView scanner / HTTP+browser scraper / Binance.
- **News:** ~70 RSS feeds (`DEFAULT_NEWS_FEEDS`) ingested into `NewsItem`
  (with sentiment + ticker extraction + `dedupKey`).
- **Macro:** 44 sources in `ECON_SOURCES` (World Bank, IMF, FRED CSV, OECD, ECB,
  Eurostat, BLS, BEA, Fed, EIA, BCB, UN Comtrade, …). Only FRED is key-gated.
- **Crypto:** Binance public endpoint (built-in connector).

No geopolitical-event, earthquake, or country-boundary source exists yet.

### 1.6 Existing chart/map infrastructure

ECharts 6 is installed and used in several widgets. **There is no geo/map
usage and no geographic dataset** — `registerMap`, `geo`, `world.json` do not
appear anywhere. This is the one genuinely new visualization capability.

### 1.7 Existing state management

Zustand (+persist middleware) for UI stores; React state + DataHub for data.
No Redux/React-Query. Investor Eye UI state = one Zustand store.

### 1.8 Existing authentication

None. Guest app. The journal carries an optional `owner` string to make auth
additive later. **Investor Eye must not require accounts.**

---

## 2. Required additions (what must be created) and non-additions

### 2.1 Must be created

1. **Geography asset** — a slimmed Natural Earth country GeoJSON in
   `public/geo/`, fetched at build/commit time (not hard-coded in components).
2. **Investor Eye data models** (only these; see §3.2):
   `Country`, `GeopoliticalEvent`, `EventEntity`, `SourceRun` (observability).
3. **Source connector tier for events** — `src/lib/investor-eye/sources/` with a
   registry + `GDELT` and `USGS` connectors, built **on `safeGet`**.
4. **Normalizer + clusterer + confidence** — pure, unit-tested modules.
5. **Ingestion orchestration** — server-side, cached, persisted, with an
   in-process cron in `instrumentation.ts` (same discipline as the others).
6. **API routes** — `src/app/api/investor-eye/*` (state, events, event detail,
   country detail, markets, layers, health).
7. **Map layer abstraction** — `src/lib/investor-eye/layers.ts` + ECharts
   adapter; business logic stays out of the visualization component.
8. **UI** — route/tab shell, `<WorldMap>`, `LayerController`, `Timeline`,
   event tooltip, country panel, "What changed" panel, data-status chips.
9. **Client state** — `src/lib/investor-eye/store.ts`.
10. **Docs** — this file + CHANGELOG/ARCHITECTURE/NAVIGATION/DECISIONS updates.

### 2.2 Must NOT be created (equivalent infrastructure already exists)

- ❌ A second market-data system → reuse `/api/indices`, `IndexQuote`, `Asset`.
- ❌ A second portfolio engine → reuse `hooks/use-portfolio-engine.ts` and
  `lib/portfolio/`.
- ❌ A second news ingester → reuse `lib/news/ingest.ts` + `NewsItem` for
  article text; GDELT is used for structured *events*, not as a news feed.
- ❌ A graph database → relational tables + JSON columns in SQLite are enough
  (ADR-011).
- ❌ A second design system / another chart library.
- ❌ Redis / a microservice / a separate map server.

---

## 3. Design

### 3.1 Layer model (conceptual, matched to this repo)

```
SOURCE (GDELT, USGS, /api/indices, /api/economics/snapshot, RSS NewsItem)
   ↓  src/lib/investor-eye/sources/*   (fetch via safeGet / existing services)
RAW
   ↓  normalize.ts                     (pure)
NormalizedEvent / MarketObservation / EconomicObservation
   ↓  cluster.ts                       (pure dedup)
   ↓  confidence.ts                    (pure scoring)
JDDS (Country, GeopoliticalEvent, EventEntity, SourceRun) + in-memory cache
   ↓  API  /api/investor-eye/*
   ↓  DataHub topics (provenance envelope)
   ↓  store.ts (Zustand: selection, layers, timeRange)
   ↓  MapLayer[] → <WorldMap> (ECharts)
```

The spec's `DataConnector` interface (§11) maps onto the existing
`src/lib/connectors/types.ts` contract. Rather than fork that contract, Investor
Eye registers its own **source adapters** shaped like `DataConnector`
(`id`, `name`, `capabilities`, `health()`, `fetch()`, `normalize()`) and reuses
`safeGet` for transport. This keeps one security path (ADR-011).

### 3.2 Database additions

All additive; no existing table is altered. JSON is stored as strings (SQLite +
Prisma has no Json column here), statuses are plain strings — matching the
existing `DataConnector`/`CustomDataset` convention.

- **Country** — canonical country entity, ISO codes + centroid + `mapName`
  (the Natural Earth `name` used to match geo features).
- **GeopoliticalEvent** — normalized event with `dedupKey` (unique, idempotent
  upsert), severity, type, categories, confidence, source provenance, JSON
  arrays for channels/commodities/sectors/securities.
- **EventEntity** — event ↔ entity join (kind: country/actor/location/...),
  written during ingestion so events are queryable by entity.
- **Relationship** — the typed, directed relationship graph edge (spec §41):
  `fromKind/fromId` → `toKind/toId`, `relation`, `relationClass`, `weight`,
  `evidence`. Unique `edgeKey` makes re-ingestion an idempotent upsert.
  **Relational, not a graph database** (ADR-011).
- **SourceRun** — one row per ingestion run per source (observability + Data
  Health): started/finished, received/accepted/rejected, error.

### 3.3 Provenance / freshness

Server computes provenance per data class; the client never invents a tag.

```
LIVE        served from a source fetch in this ingestion window
CACHED      served from JDDS/cache within its TTL
HISTORICAL  older than the live window (timeline scrubbed into the past)
UNAVAILABLE no real data — render "DATA UNAVAILABLE · last known HH:MM UTC"
```

Zero observed events with a healthy source is a legitimate `0`; a *failed*
source is `UNAVAILABLE`, never `0` (spec §14).

### 3.4 Map layer contract

`MapLayer` is a data/behavior descriptor; the ECharts adapter translates it to
series. The map component knows nothing about events/markets — it renders
whatever layers it is handed.

```ts
MapLayer {
  id, name, enabled, type, zIndex
  data: () => LayerDatum[]        // supplied by the caller, not fetched here
  tooltip(datum) → TooltipContent
  onClick(datum) → void
}
type MapLayerType = 'country-fill' | 'scatter' | 'effect-scatter'
                   | 'lines' | 'heatmap' | 'custom' | 'symbol'
```

Phase 1 activates `events` + `markets`; `conflict`, `economy`, `energy`,
`trade`, `weather`, `companies`, `portfolio` register later through the same
`registerLayer()` path with no map rewrite (spec §60).

### 3.5 Performance

- Server normalizes + clusters before anything reaches the browser.
- Grid-snapped geographic aggregation when event count is high (spec §27).
- `effectScatter` reserved for high-severity events only; plain `scatter`
  otherwise (spec §17).
- Time windows + country filters pushed to SQL; bounded `take`.
- Pure modules memoized on the client; no per-point re-render.

---

## 4. Phase 1 implementation order (maps to spec §62)

| Step | Deliverable | Status |
|---|---|---|
| 1–3 | Audit + this doc + reusable-service identification | ✅ |
| 4 | `investor-eye` tab + screen shell | ✅ |
| 5 | Map layer abstraction (`layers.ts`, `map-echarts.ts`) | ✅ |
| 6 | ECharts world map component | ✅ |
| 7 | Natural Earth geography (`public/geo/world.geo.json`) | ✅ |
| 8 | Layer architecture (registry + controller) | ✅ |
| 9 | Source/connector architecture (`sources/`) | ✅ |
| 10 | GDELT connector | ✅ |
| 11 | Event normalization | ✅ |
| 12 | Event dedup/clustering | ✅ |
| 13 | Events on globe | ✅ |
| 14 | Country selection + intelligence panel | ✅ |
| 15 | Reuse existing market data | ✅ |
| 16 | Market layer | ✅ |
| 17 | Timeline (1H/6H/24H/7D/30D) | ✅ |
| 18 | Data freshness/status | ✅ |
| 19 | Caching (server SWR + JDDS) | ✅ |
| 20 | Failure/fallback behavior | ✅ |
| 21+ | Tests, perf, then Phase 2 | ✅ |

### Definition of Done — Phase 1

Met per spec §64: screen exists in the existing design language; large ECharts
world map; interactive countries; working layer system; GDELT + USGS ingestion;
normalized + deduped events; events plotted; market layer from **existing**
infrastructure; timeline; country panel; visible freshness; source failures
don't break the page; no fake live data; caching; tests pass; no duplicate
architecture.

---

## 5. Phase 2 (implemented, following spec §63)

The deterministic foundation is extended — **no AI is required for any of it**:

| # | Item | Status |
|---|---|---|
| 2.1 | **Conflict** — conflict/military/protest events → layer | ✅ |
| 2.2 | **Economy** — real FRED CSV metrics → country-fill heatmap + metric selector | ✅ |
| 2.3 | **Energy** — energy events → layer | ✅ |
| 2.4 | **Trade** — trade/tariff/shipping events → `lines` layer | ✅ |
| 2.5 | **Weather / natural events** — USGS earthquakes → layer | ✅ |
| 2.6 | **Companies** — JDDS `Asset` universe → layer + company panel on click | ✅ |
| 2.7 | **Portfolio overlay** — reuses `use-portfolio-engine`; exposure graph | ✅ |
| 2.8 | **Market transmission** — `Event → country → channel → asset`, classified | ✅ |
| 2.9 | **Historical analogues** — real stored series + sample size + date range | ✅ |
| 2.10 | **Relationship graph** — `Relationship` model + pure builder + ECharts graph | ✅ |
| 2.11 | **AI Analyst** — 7 read-only agent tools (+ a `world` research agent) | ✅ |
| 2.12 | **Natural-language map search** — deterministic intent → layer/filter | ✅ |

### How each Phase 2 piece is wired

- **2.7/2.8/2.9** — `analytics.ts` computes exposure, transmissions and
  analogues. Transmissions render in the `TransmissionsPanel` (fed by
  `/api/investor-eye/risk`); analogues render in the `AnaloguesPanel` inside the
  event panel (fed by `/api/investor-eye/analogues`). Both were previously
  computed but never displayed.
- **2.10** — `graph-data.ts` derives edges from events (co-mention → OBSERVED),
  stored entity attributes (company→sector, company→country, country→market →
  OBSERVED) and persists them plus `EventEntity` rows during ingestion.
  `graph.ts` aggregates edges into bounded nodes/links (per-kind caps keep the
  geopolitical structure readable). `GET /api/investor-eye/graph` serves it;
  `GraphPanel` renders it with an ECharts force layout where edge colour and
  every tooltip encode `relationClass`.
- **2.11** — `agent/investor-eye-tools.ts` adds read-only tools
  (`get_world_events`, `get_country_intelligence`, `get_world_markets`,
  `get_event_detail`, `get_relationships`, `get_portfolio_exposure`,
  `get_risk_state`) spread into `TOOLS`, plus a `world` research agent. Every
  result states provenance and labels inferred links, so the model cites
  structured data instead of hallucinating.

### Definition of Done — Phase 2

Met per spec §65: multiple intelligence layers; events connected to
countries/entities; economic data integrated; energy + trade visualized;
companies/securities connected; portfolio exposure visualized; an
event→channel→market relationship exists and is classified; historical
observations are explorable; provenance is visible; the system stays
performant; all sources remain optional/fault-tolerant; the tier is reusable by
other modules.

### Performance note (shared, per-window cache)

The assembled state cache and the in-flight assembly guard are **anchored on
`globalThis` and keyed by time window** (`cache.ts`). Next evaluates each route
handler in its own module instance, so a module-level `let` gave every endpoint
a separate cache — `/state`, `/risk`, `/markets`, `/layers` each cold-ran the
full source ingestion. Sharing one cache/guard means a fan-out of routes
triggers exactly one ingestion per window. Measured: `/risk?hours=24` fell from
20–100s to ~6s after the fix.

---

## 5b. Phase 4 — feed quality, map-first layout, 3D globe

Phase 1/2 built a correct pipeline. This phase fixed what it was pointed at.

### The feed problem (measured)

| | Before | After |
|---|---|---|
| GDELT events | **0, every run** | ~400/file, 2.2s |
| Event types | `natural_disaster` only | conflict, sanction, trade, military, protest, monetary, energy, diplomatic |
| Sources contributing | USGS only | GDELT + USGS + the existing `NewsItem` rows |
| `Candles` rows | 0 | 976 (^GSPC 131 bars, BTC-USD 187) |

**Why GDELT returned nothing:** the DOC API took >13s per request while the
shared `safeGet` transport hard-caps timeouts at 10s, and it also returned HTTP
429 on short bursts — two independent failures. It now reads GDELT's **bulk
15-minute Event export**, which is ~120 KB, ~2.2s, not rate-limited, and carries
CAMEO codes, actor names/countries, Goldstein scores, mention counts and exact
coordinates. The DOC API remains a best-effort fallback only.

### New modules

| File | Owns |
|---|---|
| `cameo.ts` | CAMEO root code → event type, Goldstein → severity, **FIPS 10-4 → ISO2** |
| `relevance.ts` | investor-relevance scoring (0..1) + reasons, and the display threshold |
| `sources/news.ts` | turns existing `NewsItem` rows into events (no new feed/credentials) |
| `history.ts` | candle backfill + coverage, via the existing alerts yfinance path |

**FIPS is not ISO.** GDELT's `ActionGeo_CountryCode` is FIPS 10-4, which
conflicts with ISO for important countries (FIPS `AS`=Australia, `CH`=China,
`SZ`=Switzerland, `UK`=UK). Using the codes directly would place events in the
wrong countries, so `cameo.ts` maps them explicitly.

**Relevance, not just confidence.** `confidence` = how well corroborated;
`relevance` = does this matter to a portfolio. GDELT machine-codes everything
including local crime and sport, so without a relevance gate the map is noise.
Both are stored and the feed is ranked by relevance.

### Layout & globe

- **Map-first**: full-width hero (~55vh / ~82% viewport width), layer + timeline
  controls beneath, all detail panels stacked below the fold.
- **MAP / GLOBE toggle**: `echarts-gl` is lazy-loaded; globe mode uses
  `scatter3D`/`lines3D` (a 2D `scatter` with `coordinateSystem: 'globe'` silently
  falls back to index positioning) and a generated inline dark texture
  (echarts-gl's globe has no `map` property; its default texture is a bright
  image that hides the data). Failure falls back to the flat map.

### Performance rule learned here

Optional enrichment must never block the primary response. The candle backfill
took ~170s across 30 markets and, awaited inside `assembleState`, blocked the
first world-state fetch — the map rendered "0 events / DATA UNAVAILABLE" while
the request was still running. It is now fire-and-forget.

## 5c. Phase 5 — colour-coded layers, full-page map mode

Two presentation upgrades; no data-contract change.

### Colour-coded layers (`layers.ts`, `layer-controller.tsx`)

`LAYER_META` is still the single source of truth for the controller, and each
entry now also carries `group`, `color`, `symbol` and `hint`. `LAYER_GROUPS`
(Events · Hazards · Energy & Trade · Economy · Markets) gives the controller its
grouped strips and `groupedLayerIds()` its ordering, so a new layer appears
colour-coded with no controller edit.

**Where the colour comes from:** the adapter (`map-echarts.ts`) reads
`layerColor(layer.id)` from the same registry, so the chip and the pin can never
drift. Two deliberate rules:

- `CATEGORY_COLORED` (`conflict`, `weather`, `energy`, `portfolio`) tints points
  by *category* — those layers exist precisely to be told apart.
- `events`, `markets` and `companies` keep severity/sign colouring: `events`
  mixes categories, and for markets a red/green point is real information
  (severity, direction), not a category.

Marker `symbol` is passed to ECharts where the series supports it, and repeated
in the legend, so categories are distinguishable **without colour alone**
(spec §8 / §34). `timeline.tsx` follows the same principle: each window has a
hue (cool = short, warm = long) and the severity palette is exported from
`layers.ts` (`SEVERITY_COLORS`, `SEVERITY_ORDER`) so tick colours and legend
agree by construction.

### Full-page map mode (`full-page-map.tsx`)

An immersive view of the **same** surface: `WorldMap` fills the viewport, a top
strip keeps identity + honesty (event/market counts, DATA UNAVAILABLE · last
known), and a bottom dock keeps the colour-coded layer chips, the time window
and the selected event. It reuses `MapLayer[]`, the store and `EventPanel` — it
is a *view*, not a route.

Operational rules it follows:

- Portaled to `document.body` (a transformed/animated ancestor would scope the
  frosted glass and trap `position: fixed`).
- `document.body` scroll is locked while open; Esc exits. The screen-level Esc
  handler stands down when `fullPage` is on (the overlay owns Escape first).
- `store.fullPage` is **not** persisted: a persisted full-screen flag would trap
  a returning user in it. Only `mapMode`/`timeRange`/layers persist.

## 5d. Phase 6 — the four bugs that shipped, and their real causes

Diagnosed by loading the running page in Chrome and reading the pixels — every
one of these looked fine in the source.

### 1. The globe was a blank sphere

`echarts-gl`'s `globe` component has **no `map` property**; it takes a raster
`baseTexture`. Its built-in default is a bright photographic world image (drowns
the pins), so the first attempt substituted a 16×16 **solid dark** PNG — a dark
sphere on a dark page. It was rendering perfectly and was invisible; the pins at
its edge are what made it look like "a ring of dots".

The `geo3D`/`map3D` alternatives were considered and rejected as a rewrite.
Instead `app-geo.ts` now **draws the texture from the same GeoJSON the 2D map
uses** (`worldGlobeTexture()` → 2048×1024 equirectangular canvas → data URL):
dark ocean, lighter land, cyan coastlines, faint graticule. No asset to ship.

Two secondary bugs surfaced while building it:

- **Nesting off by one.** `Polygon.coordinates` is `ring[]` (one polygon) but
  `MultiPolygon.coordinates` is `polygon[]`. Returning "rings" for both meant a
  MultiPolygon's rings were treated as polygons, so **nothing drew** — the globe
  showed only the graticule. `geometryPolygons()` normalizes both.
- **`scatter3D` reads a third coordinate as altitude.** Sharing the 2D
  `[lon, lat, value]` data shape lifted every pin into a radiating spike out of
  the sphere. 3D series now emit exactly `[lon, lat]`; 2D keeps the third slot.

### 2. Clicking a category pin did nothing

`filterEventsLayer()` builds `conflict`, `weather` **and** `energy`, and it only
ever set `tooltip`. `buildTradeLayer` was the same. The generic `events` layer
had an `onClick`, so the bug only showed on the category layers — precisely the
pins a user clicks to ask "what is this?". All four now take `onSelect`, wired
through `buildAllLayers`. (`layers.test.ts` asserts it, since a missing optional
`onClick` is invisible to the type checker.)

### 3. "DATA UNAVAILABLE" flapping

Measured: `/api/investor-eye/state` took **15–18s** on a cold assembly (GDELT
bulk + news + USGS + markets ×6 runs) and it *awaited* that even when a good
previous state existed. Compounding it, the client equated `data === null` with
unavailable — which is also true *before the first fetch resolves*. Result: the
map painted "DATA UNAVAILABLE" on every visit, then flipped to LIVE.

- `assembleState()` is now genuine **stale-while-revalidate**: fresh cache →
  return it; stale cache → return it **now** and rebuild in the background;
  persisted last-known (cold start) → return it now and rebuild; only a genuine
  first run awaits the build. Stale serves are tagged `CACHED` +
  `refreshing: true` so the UI never calls them live.
- The screen distinguishes three states: `LOADING WORLD STATE…`,
  `LAST KNOWN HH:MM UTC · REFRESHING`, `DATA UNAVAILABLE`. The "we tried" signal
  is `HubEntry.updatedAt !== null`, not `data === null`.

### 4. The layout put the answer below the fold

Clicking a pin *did* select it — into a panel stacked under the map, off-screen.
Fixed by restructuring the hero into a **map + 360px right rail**: the selection
panel renders beside the map, and beneath it a new `LiveFeed` gives the
always-on "what is happening" stream (lenses: Conflict · All · Energy · Trade ·
Hazards, with counts). The map and rail share one bounded height
(`lg:h-[58vh]` + `lg:h-full`), so the rail can no longer overflow the viewport.
The empty "Explore the world" card is gone.

### Conflict news

GDELT's CAMEO coding under-represents ongoing conflict relative to diplomacy, so
five conflict-scoped RSS wires were added to `DEFAULT_NEWS_FEEDS` (tier 1,
category `WAR`): active-conflict language, MENA, Ukraine, shipping attacks, and
coups/unrest. No new source adapter — the existing `sources/news.ts` reads them
from `NewsItem` like any other feed.

### 5. Hovering any pin crashed the map

`tooltipFormatter` handed ECharts' own wrapper object (`{name, value, severity,
_datum}`) to `layer.tooltip()`. Every `eventTooltip` then read
`undefined.eventType`. The **click** path had always unwrapped `_datum`; the
tooltip path never did — an asymmetry that went unnoticed because a tooltip
failure only shows up on hover.

`unwrapDatum()` (`map-echarts.ts`) is now the single unwrap used by both, and
`eventTooltip` has a defensive guard (a malformed datum returns a minimal
tooltip rather than throwing). **This class of bug is invisible to `tsc`** — the
ECharts callback payload is `unknown` at the boundary — so
`map-echarts.test.ts` exercises the real formatter with wrapped payloads. It
also pins the globe data shape (`[lon, lat]`, never the 2D third slot).

### 6. Loading states and the masonry row

- The hero shows a centred dot-grid loader while the first world-state fetch is
  in flight (the rail's LiveFeed shows its own), instead of a blank map for the
  ~15s cold assembly.
- The analysis row is **CSS multi-column masonry**, not a grid. A 3-track grid
  reserves the tallest child's height in *every* track, so the short "What
  Changed" card left a large dead gap. Columns pack independently.

---

## 5e. Phase 7 — from "an event map" to an intelligence system

Phase 6 fixed what was broken. This adds the capabilities that make the surface
answer *investor* questions rather than just plotting events.

### Price reaction — the observable half of "exposure"

`reaction.ts` measures what the relevant instrument actually did after an event:
close-to-close returns at **+1/+5/+20 sessions** from the real `Candles` series,
via `GET /api/investor-eye/reaction` and `ReactionPanel` in the event panel.

The design point is the split of labour:

| Block | Says | Nature |
|---|---|---|
| "Potential exposure" | what **could** matter (channels, commodities) | inferred from text |
| "Market reaction" | what the market **did** | measured from closes |

It is deliberately not a model. There is no coefficient, no forecast, and no
synthetic fallback: when the history does not cover the window the panel says
*why* ("history starts later", "not yet measurable") instead of rendering a dash
that could be misread as "no move". The baseline is the last close on or before
the event day, and a window longer than the available history is capped at the
last real close and flagged via `daysAfter`.

### Alert rules — "tell me when…", explainably

`alert-rules.ts` defines rules as **pure predicates** over the normalized feed:
event types, severity floor, confidence/relevance floors, countries,
commodities, keywords, and an optional lat/lon/radius fence.

Two decisions matter:

1. **`matchRule()` returns reasons, not a boolean.** Every fired alert carries
   the clauses that matched (`severity critical ≥ high`, `142 km from focus`), so
   the UI never shows an unexplained badge.
2. **An empty rule matches nothing.** A predicate with no clauses would fire on
   every event and make the panel useless; refusing is the safe failure.

Persistence is `SystemConfig` JSON (the existing operator-settings convention) —
**no schema change** — and mutations go through `guardMutation`. `evaluateRules`
runs over the same cached world state the map reads, so there is no second data
path to keep consistent.

### Place gazetteer — why pins were in Kansas

GDELT and USGS carry precise coordinates. News-derived events had only a
country, so `news.ts` fell back to the **country centroid** — which put
"United States" stories in the middle of Kansas and made the map look wrong.

`places.ts` is a curated gazetteer (financial centres, major ports,
chokepoints, energy/industrial hubs) and `resolvePlace()` anchors the event
where the headline says it happened. Deliberate constraints:

- **Curated, not exhaustive.** A wrong-but-precise pin is worse than an honest
  centroid, so only unambiguous, high-signal places are listed.
- **Word-boundary matching**, so the alias list can contain short names without
  false positives.
- **Chokepoints weigh highest** (Hormuz, Suez, Malacca, Bab-el-Mandeb) — they
  drive the logistics story more than any single city.
- The country hint breaks ties, and the longest alias wins ("Strait of Hormuz"
  over "Hormuz").

The test suite asserts every place maps to a real country in the gazetteer —
which caught that `PA` (Panama) and `PS` (Palestine) were missing entirely, so
Panama Canal and Gaza events had nowhere to plot. Both were added.

### Saved views, keyboard nav, source health

- **Saved views** snapshot layers + window + projection + metric as a named
  posture. View state only — restoring cannot resurrect a stale observation —
  and layer ids are reconciled against the registry on restore.
- **Keyboard nav** (§34): `j`/`k` or ↓/↑ step the newest-first event feed and
  open each event, so the map works without a mouse.
- **Source health** (§15): the real `SourceRun` accounting surfaced as a panel,
  with a throttle shown as its own state rather than folded into "error".

---

## 5f. Phase 8 — the clustering bug, and event dossiers

### The bug: events were fusing unrelated stories

A row in the database had **16 "sources"**, among them a bicycle-retailer article
and a construction PR, attached to an International Criminal Court event.

Root cause was a three-way interaction:

1. GDELT has no headline, so `gdelt.ts` synthesizes
   `ACTOR1 / ACTOR2 — City, Region, Country`. Every event from a city shares
   that tail **verbatim**.
2. `significantTokens` tokenized the whole title, so the shared tail appeared as
   real textual evidence.
3. `shouldCluster` merged on `sameCountry && similarity >= 0.15` — a floor the
   manufactured tail cleared for free.

The fix is layered, because any one alone is insufficient:

| Layer | What it does |
|---|---|
| `clusterSignature` (contract) | A provider's own id (GDELT GLOBALEVENTID, USGS feature id) is the identity. When present, merge **only** on exact signature match — no title fuzziness may override it. |
| `stripLocationSuffix` | Removes the synthesized geo tail before tokenizing. Location stays authoritative as *location*, never as *textual evidence*. |
| `SAME_COUNTRY_SIMILARITY_THRESHOLD` | 0.15 → 0.3. A shared country is weak corroboration, not proof. |
| `dedupKeyFor` uses the signature | Without this the layers above collide: distinct signed events still hashed to the same key and persisted as duplicates (**22 of 473**). |
| `collapseDuplicateKeys` | Last line of defence — folds same-key records and unions their sources so no evidence is silently dropped. |

Measured on live data: **max sources per event 16 → 3; duplicate ids 22 → 0.**
The lesson generalizes: *never let synthesized text participate in a similarity
score*, and *when a provider gives you an id, that id is the identity.*

### Real headlines (`enrich.ts`)

GDELT publishes no headline — only the article URL. So a GDELT event could show
its actors but not what the story said. The repo already ingests ~70 RSS feeds
into `NewsItem` with real headlines.

Measured: matching raw URL strings recovered **0 of 500** events — feeds append
tracking params, vary the `www.` prefix and add trailing slashes. Normalizing to
`host + path` recovers 19, and with the full corpus loaded **202 of 461 events**
now carry a genuine headline. One DB read, no network, no new feed.

The rule holds: a miss leaves the field null. We never synthesize a headline
from the actors, because a fabricated headline reads as reporting that does not
exist.

### The dossier

`event-panel.tsx` answers, in order: **what** happened (headline/description, or
an explicit statement that the structured feed publishes none), **who** (actors
with readable type codes), **where/when** (place, coordinates, and the
*resolution method* so precision is never overstated), **why it matters** and
**what's exposed** (both labelled inferred), **what the market did** (measured),
**where it came from** (every source), and **how the story developed**
(timestamps, earliest first).

The header carries a corroboration badge — single source / corroborated /
confirmed — which only became meaningful once clustering stopped inflating
`sourceCount`.

Two supporting fixes this exposed:

- **`persistEvents` now backfills the row `id`.** The state payload previously
  carried no ids, so the entity-links endpoint 404'd on every panel open.
- **`assembleState` with `refresh=1`** returned stale cache instead of awaiting
  the rebuild, so the refresh button appeared inert.

### Icon

`ScanEye` replaces `Earth`/`Globe` across the sidebar, command palette, screen
header and full-page map — the "surveillance/intelligence" reading rather than a
generic globe.

---

## 5g. Phase 9 — recovering the story, and the fan-out bug

### Correction: the URL-join enrichment did almost nothing

The previous phase added `enrich.ts`, joining GDELT source URLs to the ingested
`NewsItem` corpus. It was reported as giving events "real headlines". Measured
against the live DB it matched **27 of 2,524 GDELT events (1.1%)**.

The number originally quoted (202 of 461) counted `news`-source events, which are
articles and *always* had headlines. The enrichment contributed essentially
nothing. The cause is structural, not a bug: the RSS corpus and GDELT's article
set barely overlap — GDELT cites publishers the feeds don't carry.

### The real fix: read the article's own metadata

GDELT publishes no headline, only the URL. So we read the page:

| Layer | File | Responsibility |
|---|---|---|
| Parsing | `article-meta.ts` | Pure HTML → `{title, description, titleSource}` |
| Fetch + cache | `article-meta-fetch.ts` | Guarded `safeGet`, per-URL cache, source fallback |

Three design decisions:

1. **Lazy, not at ingestion.** Assembly already takes ~15s; fetching hundreds of
   publisher pages inside it would make it minutes. The dossier requests one
   event's metadata when it opens.
2. **Cached per URL, permanently** (bucketed `SystemConfig` JSON). Any URL is
   read at most once, ever — so the network cost is per-article, not per-view.
3. **Honest failure.** A paywall, bot wall, timeout or non-HTML response yields
   `available: false` with a *reason*. The panel keeps saying "no headline
   available"; nothing is synthesized.

Parsing details that matter: only `<head>` is searched (so a page quoting
`og:title` in its body can't inject metadata), `og:` → `twitter:` → `<title>` →
`<h1>` in that order, entities decoded, and bot-walls / consent screens /
site-name-only titles rejected.

### The fan-out bug

Building the above surfaced something worse than the original clustering bug.

**GDELT codes one row per actor dyad.** A single article becomes many events —
`CHINA / AUSTRALIA`, `BEIJING / UNITED KINGDOM`, … — and one article produced
**37 events**. Measured: **62.7% of events shared an article URL**.

The signature gate from the previous phase correctly stopped *unrelated* stories
fusing, but left this fragmentation in place: each dyad had a distinct
GLOBALEVENTID, so nothing merged.

The fix is a third identity regime, most-precise first:

| Regime | Signal | Rule |
|---|---|---|
| 1 | **Article URL** | Same normalized URL + same type → same event. A URL is definitive identity; actors and titles are irrelevant. |
| 2 | Provider signature | Exact match only (GDELT id / USGS feature id). |
| 3 | Fuzzy | Title similarity + country, for articles with no URL. |

Scoping by event type is deliberate: one article read as both a `sanction` and a
`trade` event keeps both readings rather than silently dropping one.

Measured: **461 → 338 events** in a 24h window, and corroboration became
meaningful again — a rates story now shows Seeking Alpha + Investing.com + CNBC
instead of one outlet repeated 30 times.

The generalizable lesson: *when a provider gives you a document identity, that
outranks its per-row event identity.* GDELT's row id identifies a coded action,
not a story — the URL identifies the story.

### Readable titles

GDELT's synthesized `ACTOR1 / ACTOR2 — City, Country` rendered as code fragments.
`formatEventTitle` restructures the same fields into a sentence (*"POLICE in
Washington, District of Columbia, United States"*) without inventing anything,
and leaves real headlines untouched — including one that merely contains a `/`.

---

## 5h. Phase 10 — where events are plotted

### The Kansas problem

`CountryDef.lon/lat` is a country's **geographic centroid**. That is a reasonable
anchor for a country-wide event, but wrong for a policy event: "the Fed raises
rates" plotted at the US centroid lands in Kansas, and "Brazil's central bank
cuts rates" lands in the Amazon. In a 7-day window, **83% of news-derived events
sat at a country centroid**.

The insight is that *event type implies a location kind*:

| Event is about… | Meaningful anchor | Why |
|---|---|---|
| a place (port, chokepoint, city) | that place | named in the text |
| a physical incident (conflict, quake, storm) | its own coordinates | has a real location, usually NOT the capital |
| a government / central bank / regulator | the **capital** | the story is reported *from* there |

`geo-resolve.ts` encodes that as a preference order — named place → exact provider
coordinate → capital (policy types only) → centroid — and returns a `geoMethod`
alongside the coordinate so the UI can state its own precision.

**Deliberately excluded from capital-anchoring:** `conflict`, `military`,
`natural_disaster`, `energy`, `shipping`. Forcing a missile strike to a capital
would be a regression, and the tests assert that.

### Measured result

| | Before | After |
|---|---|---|
| news events at country centroid | 83% | **34%** |
| events with a `place` anchor | 11 | **44** |
| events capital-anchored | 0 | **88** |

### A guess must not look like a fix

A centroid pin previously looked identical to an exact one. Now centroid points
are hollow, dashed and slightly smaller, with a legend entry and a tooltip line
("Location is the country centre only (shown hollow)"), and the dossier prints
the method verbatim.

### No migration needed

`reResolveEventLocation` re-derives the anchor when an event is read, so
historical rows pick up the capital rule on the next load. Resolution is
deterministic and cheap, which is why it is recomputed rather than migrated — and
an exact provider coordinate is never second-guessed. `jdds.db` therefore needed
no new columns for this phase.

### Gazetteer gaps found by probing real headlines

Extending `places.ts` with ~120 entries (ports, rivers, commodity regions) was
driven by running the resolver against actual headlines rather than guessing. That
probe also caught three countries — **Djibouti, Somalia and Eritrea** — missing
from `countries.ts` entirely, so Red Sea shipping events had nowhere to plot.

---

## 5i. Phase 11 — the analyst, where the question is asked

The 7 read-only Investor Eye agent tools (`agent/investor-eye-tools.ts`) already
existed and were already registered in the shared tool set — but the only way to
reach them was the chat, so a user had to leave the event and re-describe it. The
dossier now has an **Analyst** section that runs the world analyst against the
selected event.

**What makes it grounded rather than generative.** `event-record.ts` renders the
event as a factual briefing and the model is additionally allowed to call the
read-only tools. Three deliberate choices:

1. **Absent fields are omitted, not placeholder-ed.** Printing `Location: —`
   invites the model to fill the gap; omitting the line does not.
2. **Location precision is always stated** (`country capital (policy event)`),
   so the model cannot imply more accuracy than we have.
3. **Text-derived exposure is labelled `(derived)`**, keeping observation and
   inference separable — the same distinction the UI makes.

The system prompt repeats the platform's honesty rules: label inferred exposure
as *potential*, quote provenance, and never invent an event, number, headline or
source.

**Offline-honest.** `POST /api/investor-eye/explain` returns **503** when no LLM
is configured, and the panel renders "No AI provider is configured" — verified in
the browser. It never fakes an answer.

**Why the prompt builder is its own module:** the route handler should be thin,
and the shape of what the model receives is a correctness concern. If actors,
provenance or the precision line silently disappeared in a refactor, the analyst
would start guessing — so it is pure and unit-tested (6 tests).

---

## 6. Conflicts with the spec, and how they were resolved

| Spec assumption | Repository reality | Resolution |
|---|---|---|
| Multi-route app (`/investor-eye`) | Single page + tab state machine, no screen router | Added an `investor-eye` **tab** (the repo's route convention). |
| `DataConnector` contract as specified | A different `DataConnector` already exists in `lib/connectors/types.ts` | Did **not** fork it; source adapters reuse `safeGet` and mirror its shape. |
| PostgreSQL / graph DB | SQLite-only JDDS; ADR-010 forbids casual new stores | Relational tables + JSON columns; documented as ADR-011. |
| Company/securities/country entities | `Asset.country` is a string; no `Country` model | Added `Country`; linked existing `Asset`/markets by ISO code without altering them. |
| Economic metrics for arbitrary countries | `ECON_SOURCES` exposes curated countries/indicators | Reuse it; show only what it can actually return, else `UNAVAILABLE`. |
| ACLED conflict data | Requires account/API auth | **Optional** — not wired; GDELT covers Phase 2 conflict so nothing breaks without it. |
