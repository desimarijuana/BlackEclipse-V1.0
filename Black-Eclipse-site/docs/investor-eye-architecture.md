---
title: Investor Eye — Architecture & Audit
status: Current
last-verified: 2026-10-12
---

# Investor Eye — Architecture & Audit

**Who this is for:** anyone implementing or extending Investor Eye (the
financial/geopolitical world-state surface). Read §1–2 for the audit, §3 for the
design, §4 for the Phase 1 build order, §5 for Phase 2, and §5b–5m for the
later presentation/quality passes (globe, colour-coded layers, full-page mode,
the runtime bugs fixed after them, price reaction/alerts/gazetteer, event
dossiers, clustering recovery, event plotting, the AI analyst, recurrence,
data-source governance + NASA FIRMS, the layer/pin corrections that surfaced data
already in the database, the globe's visual system + the two bugs that fixing it
exposed, the surface skins, the pin-glyph accuracy fixes, the living sky, and
finally the NASA EONET multi-hazard source + a per-source ingestion circuit
breaker).

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

   The committed `public/geo/world.geo.json` carries a deliberate **point of
   view**: the whole of Jammu & Kashmir (including the Kashmir Valley, Jammu and
   Ladakh) is drawn as Pakistan, while Aksai Chin remains with China. Natural
   Earth ships the default (division along the Line of Control) view, and the
   `scripts/fetch-world-geo.mjs` regeneration path reproduces *that default* — it
   does **not** re-apply this policy, so any regeneration must be followed by the
   Kashmir splice. India and Pakistan are the only two features affected; the
   shared boundary is a single clean edge (no slivers, no gaps), and the
   server/client point-in-polygon lookups (`admin-boundaries.ts`,
   `app-geo.ts`) inherit it automatically.

   The same asset also carries the **Gaza Strip**: Natural Earth's 110m layer
   omits Gaza entirely (it renders as unclaimed blank and matches no country), so
   the 10m Gaza polygon is added to the `Palestine` (`PS`) feature — which becomes
   a `MultiPolygon` of West Bank + Gaza — and subtracted from Israel's coarse
   polygon. This is a geometry completeness fix, not a political statement; like
   the Kashmir splice it is reverted by a plain `fetch-world-geo.mjs` run.
2. **Investor Eye data models** (only these; see §3.2):
   `Country`, `GeopoliticalEvent`, `EventEntity`, `SourceRun` (observability).
3. **Source connector tier for events** — `src/lib/investor-eye/sources/` with a
   registry + `GDELT`, `USGS`, news-derived and `NASA FIRMS` connectors, built
   **on `safeGet`**, each with a `source-catalog.ts` governance entry.
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
| 2.13 | **Event heatmap** — severity-weighted ECharts `heatmap` series, 2D geo only (globe keeps pins), `visualMap` legend + per-event tooltip | ✅ |

### How each Phase 2 piece is wired

- **2.7/2.8/2.9** — `analytics.ts` computes exposure, transmissions and
  analogues. Transmissions render in the `TransmissionsPanel` (fed by
  `/api/investor-eye/risk`); analogues render in the `AnaloguesPanel` inside the
  event panel (fed by `/api/investor-eye/analogues`). Both were previously
  computed but never displayed.
- **2.10** — `graph-data.ts` derives edges from events (co-mention → OBSERVED),
  stored entity attributes (company→sector, company→country, country→market →
  OBSERVED) and persists them plus `EventEntity` rows during ingestion.
  The rebuild is **fire-and-forget and throttled** (`state.ts`, once per 10 min)
  and never runs on the world-state response path: awaiting it froze every HTTP
  request on the single Node event loop. `persistEventEntities` also pre-loads
  the existing `(eventId, kind, entityId)` keys in one query rather than a
  `findFirst` per reference — the per-ref check measured ~50 s for an ~800-event
  window and starved the loop.
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

## 5j. Phase 12 — recurrence, and honest corroboration

### A single event is not intelligence

"Explosion near Hormuz" means something quite different when it is the fourth
incident there this week. `situations.ts` groups the window's events into
SITUATIONS by **type + country** and reports count, span, peak severity, a
severity trend, and whether it is escalating.

Two mistakes were made and fixed while building it, both caught by looking at
live output rather than the unit tests:

1. **Bucketing by raw place fragmented one situation four ways.** The same
   conflict appeared as separate "situations" for `US`, `United States`,
   `Washington` and `Washington, D.C.` — providers disagree on granularity, so a
   place string is not a stable grouping key. Bucketing moved to **country**.
2. **And that produced the opposite error.** Country bucketing then labelled 147
   US conflicts as `Washington, D.C.` (the most common place), which implies they
   all happened there. The label is now the **country** — what the count actually
   covers — with the top place and the count of distinct places as *separate*
   context:

   > 140× conflict in United States · across 61 places, most often Washington, D.C.

The lesson generalizes: **the label must describe the unit you counted, not the
most interesting member of the set.**

**"Escalating" is deliberately hard to earn:** 3+ occurrences *and* a genuinely
rising severity trend. Two points is a comparison, not a trend. It is described
in the UI as a description of the trend so far, never a forecast.

### Corroboration after the article-identity fix

The article-identity clustering (5f) means one article can legitimately back
several captured sources, so the old badge — which used `sourceCount` — began to
**overstate** corroboration: "confirmed · 15" could be one story cited fifteen
times.

The badge and the Sources block now count **distinct outlets** and distinct
article URLs, and state which case applies ("Multiple citations of the same
article — one outlet"). A number that had quietly become misleading is honest
again.

---

## 5k. Phase 13 — data governance, and NASA FIRMS

Two additions the earlier phases deferred: the spec's licensing/attribution
requirement (§6/§36) had no home at all, and the hazard layer had one source.

### The source catalog — making licences a build-time invariant

`source-catalog.ts` is a separate registry from the adapters, on purpose. An
adapter answers *"how do I fetch and normalize this?"* — a question about code.
The catalog answers *"am I allowed to use this, and what must I say about it?"* —
a question about law. Fusing them would mean a licence question could only be
answered by constructing a fetcher, and a new adapter could ship with nobody
noticing it had never declared a licence.

Each entry records `provider`, `license`, `licenseUrl`, `termsUrl`,
`commercialUse`, `requiresApiKey`, `attributionRequired`, `attribution`,
`rateLimit` and `dataFreshness`. "Public API" does not imply "free for
commercial use", so nothing is inferred from a URL being reachable — each entry
records what the provider actually states, with a link an operator can check.

**The invariant is enforced by tests**, not by convention:
`source-catalog.test.ts` asserts every *registered* source has a catalog entry
and that the entry's `requiresApiKey` agrees with the adapter's
`requiresCredentials`. Adding an adapter without declaring its licence fails CI.
A second test asserts the reverse — no catalog entry without a registered
adapter — so the catalog cannot document a fiction.

The one deliberate exemption is `local: true` (the app's own RSS corpus): it is
read from JDDS, not fetched from a third party, and its upstream feeds declare
their own terms individually in `DEFAULT_NEWS_FEEDS`.

`/api/investor-eye/health` now joins run accounting with governance metadata and
returns the centralised `attributions` list; `SourceHealthPanel` renders the
spec §19 table columns (source · category · auth · licence · updated · state)
with a per-source detail expansion and an attribution footer. A source that can
run without a declared licence is shown as an explicit **governance gap** rather
than a blank cell that would read as "nothing required".

### NASA FIRMS — the second hazard source

`firms.ts` reads FIRMS' **keyless global archive CSV** (24h/48h/7d). The Area
API was deliberately not used: it needs a free `MAP_KEY`, and Investor Eye must
work with zero configuration.

The design point is that **the raw feed is pixels, not fires**. A 24h global file
carries ~25,000 single-pixel detections; one real wildfire produces dozens to
hundreds of adjacent ones. So detections are snapped to a grid and merged at
**ingestion** — never in the browser — into bounded clusters carrying the real
detection count and summed Fire Radiative Power (FRP).

Three details that are easy to get wrong, all caught by testing against live data:

- **The clustering grid needs a `cos(lat)` correction.** A degree of longitude is
  only ~19 km at 70°N versus ~55 km at the equator, so an uncorrected grid
  fragments a polar fire into cells that each fall below the minimum detection
  count and vanish. The cell must be *wider* in degrees near the poles.
- **Empty CSV cells are not zero.** `Number('')` is `0`, so a missing coordinate
  would become a real-looking detection on the equator, and a missing `acq_time`
  would become midnight. Both are now rejected before coercion.
- **A feed endpoint is not an article.** `dedupKeyFor` treats a source URL as
  *article identity*. Stamping the FIRMS feed URL onto every cluster made all 400
  collapse to one event. The cluster now carries no source URL; its identity is
  the grid-cell signature.

FRP thresholds are anchored to the published live distribution (median ≈ 231 MW,
p90 ≈ 1054 MW, p99 ≈ 5175 MW) rather than picked to look dramatic — FRP is a
measured physical quantity, so severity from it is an observation, not a model.

### Exact country attribution (`admin-boundaries.ts`)

FIRMS carries no place text, so a fire's country had to be derived from its
coordinate. `resolveFireCountry` originally used the nearest gazetteer
**centroid**, which is badly wrong for a large country: a fire in eastern Siberia
is thousands of km from Russia's centroid. Measured on live data, centroid
matching attributed **62 of 400** clusters (15%).

`admin-boundaries.ts` runs a real **point-in-polygon** test against the *same*
Natural Earth GeoJSON the map already ships — no new asset, no new dependency.
That alone lifted the rate to 167/400. The remaining loss was a second, subtler
bug: the boundary asset (173 features) is broader than the curated country
gazetteer, so a proven hit in Mozambique or Angola was being discarded because
`countryByIso2` had no entry. Using the boundary's own ISO2/name when the
gazetteer misses took it to **397 of 400** — the three remaining are genuine
ocean points, which deliberately stay unlabelled.

### Hazard category, and splitting the layer

`natural_disaster` covered both earthquakes and fires, so one layer showed both.
A new provider-stated `category` field (`earthquake` / `fire`) separates them:

- The `fires` layer is registered separately (spec §21 lists Fires and
  Earthquakes independently), with its own colour and marker.
- `shouldCluster` refuses to merge two *different* known categories, so an
  earthquake can never fuse with a fire.
- The split is **exclude-by-category**, not require-category: rows persisted
  before the field existed carry no category, and they keep their original
  `weather` layer rather than disappearing. No migration was needed — the same
  "re-derive on read" reasoning as `reResolveEventLocation`.

### Measured result

| | Before | After |
|---|---|---|
| Hazard sources | 1 (USGS) | 2 (+ NASA FIRMS) |
| Fire clusters (24h) | — | 400 (bounded from ~25,600 detections) |
| Fire clusters with a country | 62/400 (15%) | **397/400** |
| Sources with declared licence/attribution | 0 | 4/4 (enforced by test) |
| FIRMS fetch / normalize | — | ~3.1 s / ~0.2 s |

---

## 5l. Phase 14 — showing the data that already existed

Three problems were reported against the live UI. Two were presentation; one meant
a large part of the feed was never drawn at all.

### Layers matched type, but the signal lives in channels

`classify.ts` assigns each event **one** type (the strongest signal) but **many**
channels. The domain layers filtered on `eventType` alone, so an event typed
`conflict` that carried the `Shipping & Logistics` channel was invisible to the
Shipping layer — a Red Sea attack is exactly that shape.

Measured on a live 24h window:

| Domain | Typed | Carries the channel | Layer showed before |
|---|---|---|---|
| Shipping | 11 | 28 | 11 |
| Energy | 29 | 46 | 29 |

`buildDomainLayer` now matches **type OR channel**. A layer is a lens, not an
exclusive bucket: the same event legitimately appears in Conflict and Shipping,
because it genuinely is both. Trade lines follow the same rule.

Two new layers were added because the extraction already existed and nothing drew
it: `shipping` (its own layer rather than folded into Trade) and `commodities`
(any event naming a traded commodity). `commodities` is deliberately the one layer
with no type/channel scope — naming a commodity *is* the membership test.

### Pins were unreadable

The markers were 6–13px flat dots with a 0.5px border and `opacity: 0.9`. On a
dark map that reads as noise rather than "something is happening here". Each pin
now has:

- a larger core sized by severity (8–18px, was 6–13),
- a dark contrast ring, so overlapping pins never bleed into one blob,
- a severity-sized coloured glow (5–26px), so a critical event looks heavier
  before you hover it.

The hollow/dashed convention for country-centroid anchors is unchanged — that cue
still separates "we know the country" from "we know the place".

### The stale-client trap (why events existed on the map but not in the DB)

After the `category` column was added, the running dev server still held the
Prisma client generated *before* it. Every FIRMS write threw, and `persistEvents`
catches per-row errors by design (one bad row must not abort the batch) — so the
failure was silent: the map showed 374 fires that existed nowhere in the database,
and every payload event had no `id`. A fresh process persisted correctly
(374 rows written). **Restart the dev server after `prisma generate`**; the
per-row catch is correct for resilience but hides a total-write failure.

---

## 5m. Phase 15 — the globe gets a look, and two bugs it exposed

> **Partly superseded by §5n.** The near-black palette, the halos and the
> atmosphere-rim decision below describe the `black` skin as it stood before the
> skins existed. The pins are now category **glyphs**, not haloed dots (the halos
> were removed — a larger copy of a glyph behind it reads as a blob that erases
> the shape), the rim is an emission layer rather than `atmosphere`, and the
> default surface is the blue `glow` skin. The reasoning about why the TEXTURE
> carries the look, and the two runtime bugs, still hold.

The globe worked but read as a flat, bland sphere. Making it *look* like a
financial intelligence planet surfaced two real defects.

### The visual system

| Element | Before | After |
|---|---|---|
| Ocean | flat `#0b1220` | near-black vertical gradient (`#01030a` → `#04101f`) |
| Land | mid-tone `#2b3442` | dark slate `#0d1726`→`#122136` |
| Coastline | 1px cyan stroke | blurred shadow pass UNDER the land, leaving a halo that hugs the coast |
| City light | none | deterministic stipple on land only |
| Stars | none | canvas starfield: 3 depth tiers + two nebula washes |
| Globe rim | none | `atmosphere` cyan rim glow (now: an additive **emission layer** — `atmosphere` peaks exactly on the silhouette, so it can only ever draw a hard ring) |
| Pins (globe) | single flat dot | **category glyph + a faint critical ring** (the halo discs were removed — see §5n) |
| Pins (2D) | 6–13px flat, 0.5px border | 8–18px, dark contrast ring, severity-sized glow |
| Trade routes | hairline | wide translucent glow pass under a bright pass |

Two decisions carry most of the look:

1. **The texture does the work, not the lighting.** `echarts-gl` lights the globe
   as a surface (`shading: 'lambert'`), so flat fills come out muddy. A dark
   texture + LOW ambient (`0.35`, down from `1.1`) is what keeps the planet
   near-black with only the coastline and pins glowing. A high ambient washed the
   whole sphere into a bright blue ball — the first attempt did exactly that.
2. **A glow needs a white-hot core.** The first pin attempt used one colour for
   both core and halo, which rendered as dark-centred **donuts**. A real light
   source is a bright point inside a coloured halo, so the core is the accent
   lightened 72% toward white (`lighten()`) and the halo keeps the severity
   colour. Two halo radii (tight + wide) give the falloff a single halo cannot.

Also deliberate: `autoRotate` is **off**. The pins are click targets, and a
moving target is a broken interaction.

### Bug 1 — a map-local loader was covering the entire app

`WorldMap` rendered `TopLoader` as its loading state. `TopLoader` *portals to
`document.body`* at `z-[45]`, so whenever the map was still initialising the
overlay covered the whole application at a stuck `95%` — sidebar and all. It is
now a scoped inline loader inside the map box, and globe initialisation has a
20 s ceiling that falls back to the flat map rather than spinning forever.

This was invisible in the original implementation because the flat map loads
instantly; it only appeared once the globe path could take seconds.

### Bug 2 — a removed import left a `ReferenceError`

While replacing the loader the `TopLoader` import was dropped but one usage
remained, so `WorldMap` threw `ReferenceError: TopLoader is not defined` inside a
`useMemo`. React's error boundary then left the previous frame on screen, which
is why the page showed a frozen loader rather than an error. The globe-specific
test now asserts the halo contract so a future edit cannot silently remove it.

### FIRMS flakiness

Measured: the 24h global CSV is ~1.6 MB and normally lands in ~3 s, but the
shared transport caps timeouts at 10 s and the feed occasionally exceeds it,
which silently emptied the hazard layer for a whole cycle. `firmsSource.fetch`
now does one bounded retry, and only for a *transient* transport error (a 4xx/5xx
is not retried — the request itself would be wrong).

---

## 5n. Phase 16 — surface skins, accurate pin glyphs, a living sky

Three requests: the map/globe should be **blue**, the background should be
**alive with shooting stars**, the pins should look like the thing they mean, and
there should be a **simple button to switch between the plain black surface we
first had and the new glowy one**.

### The skin switch (`MapSkin`)

`MapSkin = 'black' | 'glow'`, persisted in the store alongside `mapMode` and
captured in saved views. `MapControls` (`src/components/investor-eye/
map-view-controls.tsx`) is the single place both choices are made, rendered in the
hero header **and** the full-page dock — it exists because two hand-rolled copies
is how one surface ends up missing a control the other has.

The same control strip carries a **STARS ON/OFF** toggle (`showStars`). The
starfield is deliberately **unmounted**, not hidden — a hidden canvas keeps its
rAF loop running, and this screen already runs a WebGL render loop. With stars
off, a skin-matched CSS radial gradient paints the sky so the surface still
looks intentional rather than like a missing layer.

- `black` is the original terminal look: **mid-grey** land (`#4b5058`→`#5a606a`)
  on a `#1a1c20` ocean, hairline borders, no shadow, no globe aura, no bloom, and
  a **still** flat-black sky. The grey is deliberate — the first version was
  near-black (`#141416`), which under `lambert` lighting with low ambient
  collapsed into a featureless dark ball. It also carries a higher ambient
  (0.85) and no shadowing so the grey actually reads. Measured mean luminance
  55 vs 14 before; land sits at 84–119 against an ocean of 38.
- `glow` (default) is the blue lit planet: translucent blue continents that let
  the starfield read through, cyan coastlines, blue globe ocean/land, an additive
  emission aura and post-process bloom.

A skin is pure view state, so switching it re-renders the option in place. The
globe texture is **keyed by skin** (`globeTextureRef = { skin, url }`) — the
obvious `if (globeTextureRef.current) return` guard silently kept the blue planet
in the black skin after a switch. `texVersion` state bumps when a texture
finishes drawing so the update effect re-renders without rebuilding the chart.

### The pin glyphs were wrong, and it was three bugs

Measured by rasterising every `SYMBOL_PATHS` glyph and sampling ink coverage at
known radii — not by eye.

1. **Same-winding holes.** A canvas/SVG fill uses the **nonzero winding rule**. A
   subpath meant to be a *hole* must run the **opposite** way round, or the hole
   fills in. `seismic`, `portfolio` and `risk` all wound their cut-outs the same
   way as their outer shape, so an earthquake, a portfolio and a risk all drew as
   **solid blobs** — indistinguishable from the catch-all dot.
2. **A single near-full arc.** `M50,14 A36,36 0 1,1 49.9,14 Z` (a circle drawn as
   one arc back to a point 0.1px away) renders **off-centre and lumpy**. Every
   circle is now a pair of 180° arcs.
3. **The catch-all drew on top.** The `events` layer sat at `zIndex: 30`, *above*
   the category layers at 25, so its dot was painted over the conflict/fire/
   energy glyphs. It is now 15: it is background texture, and the shapes that say
   what each event *is* have to win. `wave` and `exchange` also had overlapping
   subpaths that merged into unreadable shapes.

The regression test asserts the winding directly (opposite sweeps for arc rings,
opposite signed area for `risk`'s polygon hole, an even arc count), and a
separate test pins the z-order relationship.

### The living sky

`Starfield` gained the same `skin` prop. In `glow` it animates; in `black` the
loop is **never started** and one still frame is painted, which is the point of
that skin.

Two fixes made the animation actually visible:

- **Meteors were too rare.** The first timer was 6–18 s, so the sky looked dead
  on arrival. It now spawns from 0.6 s and then every 3–8 s, up to three in
  flight.
- **The loop assumed 60 fps.** `dt` was hard-coded to `1/60`, so drift and
  meteors ran at the wrong speed on any other refresh rate. It now uses real
  elapsed time, clamped to 50 ms so a backgrounded tab (where rAF pauses) never
  teleports stars when it resumes.

Measured on the glow skin: sky brightness swings `254 → 578` over 40 s (drift +
meteors); the black skin is **constant at 335**.

The `black` surface is GREY rather than black for the same reason the sky is
flat there: a terminal surface should still be readable. Its palette lives in
`GLOBE_PALETTES.black` in `app-geo.ts`.

---

## 5o. Phase 17 — a globe that fills the map, and country names on both projections

Two presentation requests: make the globe **big**, and **show country names** the
way the reference screenshot does.

### The globe was small because the camera was a magic number

The option hard-coded `globeRadius: 86` and `distance: 200`. Those are independent
of the container, so the sphere projected to ~65% of the viewport height on any
screen — a small ball floating in a large map.

The fix derives the camera distance from the live container box
(`globeViewDistance` in `map-echarts.ts`). The geometry: a sphere of radius `R`
whose centre is `D` from the camera has silhouette half-angle `asin(R/D)`, so its
screen radius as a fraction of the viewport half-height is

    R / (√(D² − R²) · tan(fov/2))

Solving that for a target fill (fraction of the **shorter** viewport dimension)
gives `D`; echarts-gl measures `distance` from the **surface**, so `R` is
subtracted. A sphere images isotropically, so only the shorter dimension
constrains it — which is why the framing is **resolution-independent** and depends
only on the aspect ratio. `WorldMap` feeds the box from the same `ResizeObserver`
that already drives `resize()`, so the globe re-frames when the hero/full-page
layout changes.

`GLOBE_RADIUS` (100) is now the only globe modelling constant; the camera is
always derived.

### Country names via a shared label series, not `geo.label`

`geo.label` would only label the 2D projection — echarts-gl's `globe` component
has no component-level label support at all. So country names are a **scatter
series** at the gazetteer centroids whose only visible element is the label
(`scatter3D` on the globe, `scatter` in 2D). One series, both projections.

- Data comes from `COUNTRIES` (curated short names + stable centroids), not the
  raw Natural Earth `ADMIN` names, so a label reads "United States", not "United
  States of America", and the same centroid is used everywhere.
- `silent: true` so the labels never steal a click from the pins underneath.
- The series sits at `z: 4` — above the land, below the event pins.

`showCountryLabels` (default `true`) turns it off, and a test asserts the series
is emitted in both projections with exactly `[lon, lat]` on the globe (the same
altitude rule every globe point follows).

### Label styling, and two traps that made them invisible

Names are deliberately **small (9px) and light**: they are background context, not
headlines. The font names the app's own sans stack so they match the terminal
chrome. Legibility comes from a **soft shadow**, not a stroke — `textBorderColor`
paints a hard outline around every glyph, which at 9px smears the letterforms and
looks worse, not better.

Two separate bugs made the first attempt render **nothing**, and both are worth
recording because the failures were silent:

1. **`itemStyle.opacity: 0` hides the label too.** The marker dot was hidden that
   way, but the label inherits the item's visual opacity, so the text existed in
   the display list at alpha 0. The fix is a transparent FILL
   (`color: 'rgba(0,0,0,0)'`) plus an explicit `label.opacity: 1`.
2. **`symbol: 'none'` skips the label entirely.** ECharts' `SymbolDraw` (2D) and
   echarts-gl's `PointsBuilder` (globe) both refuse to build a label when the
   symbol is `none` — the label is attached to the symbol, so removing the symbol
   removes it too.

### Globe zoom pixelation

At high zoom the sphere magnifies a small region of the surface texture, so a
2048×1024 texture stair-stepped once the camera pushed in. The surface and
emission textures are now **4096×2048** (the largest size WebGL guarantees, and
power-of-two so claygl keeps its mip chain), and the stroke widths, bloom blur,
graticule and stipple are scaled with the resolution so the on-screen weight is
unchanged while the geometry underneath is twice as fine.

### Globe country highlighting (hover + click)

The 2D `geo` component highlights a hovered country natively, but the 3D `globe`
is a single textured sphere with **no per-country geometry** — it emits no geo
hover or click event at all. To give the globe the same behaviour:

1. a screen point is raycast onto the sphere (`viewGL.castRay`),
2. the hit is converted to lon/lat with the globe's own `pointToData`, and
3. the point is tested against the loaded GeoJSON (`countryIsoForPoint`).

The hovered country's rings are drawn as a `lines3D` **polyline** outline, and a
click selects the country (opening the same country panel the 2D map does).

A sharp edge: `ViewGL.castRay(x, y, out)` merely forwards `out` to the camera and
returns that same value — passing `undefined` yields `undefined`, not a ray. So a
minimal ray object is supplied and filled in place, and the sphere intersection is
done directly (`|o + t·d|² = R²`) rather than importing claygl's `Ray` for four
lines of algebra.

`NAMES ON/OFF` sits in the map view controls beside the projection, skin and
starfield toggles, and is persisted in the store and saved views.

---

## 5p. Phase 18 — the third hazard source, and a per-source circuit breaker

Two gaps remained after §5k: the hazard layer still carried only two
single-phenomenon providers, and a provider that was **deterministically down**
still cost its full transport timeout on *every* ingestion cycle.

### NASA EONET — the wide hazard source

`firms.ts` and `usgs.ts` cover fires and earthquakes only. **NASA EONET v3**
(`sources/eonet.ts`) is a keyless, global, JSON feed of *curated* natural events —
severe storms, floods, volcanoes, droughts, dust/haze, landslides, sea/lake ice,
snow, temperature extremes, water colour and some man-made incidents — each citing
the agencies that reported it. One request adds the missing phenomena and doubles
as a corroboration source.

Design decisions, all following the established adapter discipline:

- **Provider identity is the identity.** EONET's own event id is used as the
  `clusterSignature`, so an event is never fuzzy-merged with news text (the same
  rule that fixed the §5f fusing bug).
- **Geometry is an observation history.** The most recent observation is the
  current position. Polygon events (large fires, sea ice) are reduced to a
  representative centroid — dropping the GeoJSON closing vertex so the point is
  not biased toward one corner — which is a coordinate derived from provider
  geometry, not a fabricated one. A `(0,0)` null-island sentinel is rejected.
- **Severity uses the provider magnitude only where the unit is known.**
  Earthquakes reuse the established magnitude scale; storms use a
  tropical-cyclone band (`severityFromWindKnots`, with mph/m/s normalized to
  knots). Everything else falls back to the honest text lexicon — a storm value
  in an unknown unit is never mis-scaled as an earthquake.
- **A feed link is fine; an agency URL is not.** Only the unique EONET event link
  is carried as a source URL (it is safe as article identity). The corroborating
  agency URLs are recorded by name/id *only* — a shared agency page (one InciWeb
  URL across a region) would otherwise fuse unrelated events, the exact §5k FIRMS
  trap.

`eonet` also declares its licence in `SOURCE_CATALOG`, so the governance
invariant (`source-catalog.test.ts`) still holds: an adapter cannot ship without
its licence. Attribution is required and surfaces through
`/api/investor-eye/health`'s `attributions`.

### The per-source circuit breaker (`circuit-breaker.ts`)

Ingestion already isolates one source's failure from the others, but a source
that keeps failing deterministically (a host that always times out, a provider
returning 5xx) still costs its full 10s transport timeout on every cycle. With
several sources that is minutes of wall-clock per assembly spent waiting on
something known to be broken.

`runSource` now consults a breaker keyed by source id: after
`failureThreshold` (3) consecutive failures the source is **short-circuited** —
skipped without a network call — for a cooldown (5 min), then allowed one probe;
any success closes it immediately. Both `fetch` failures and `RateLimited`
throttles count (a provider hammering us should not be retried at full rate), and
an honest **empty** result counts as success.

The honesty rule is explicit: an open breaker does **not** invent a source
result. The skipped run is reported with the real reason and failure count
(`circuit open — N consecutive failures; retry in Xs`), so a short-circuit is
never displayed as a healthy-but-quiet source. State is anchored on `globalThis`
(same discipline as `sources/registry.ts` and `cache.ts`) so every route bundle
shares one breaker per source; `resetBreakers()` is the test seam.

Tests: `eonet.test.ts` (19 — category/severity/geometry/identity),
`circuit-breaker.test.ts` (6 — open/half-open/close/re-open/independence), plus
the unchanged full suite (2473 TS tests green, `tsc` clean).

---

## 5q. Phase 19 — why conflicts "sometimes don't appear", and the fix

A reported symptom: the Conflict layer was intermittently empty. Audited against
the code, it was not one bug but five, and the dominant one was structural.

### Root causes

1. **GDELT was fetched as a single 15-minute snapshot.** `lastupdate.txt` names
   only the NEWEST export file, so the map showed events GDELT coded in the last
   quarter hour — an ongoing conflict fell off a "24h" window almost immediately.
2. **`assembleState` rebuilt from live fetches only and never read back the DB.**
   Once a source cycle was thin (or failed), previously-seen events vanished.
3. **The relevance gate dropped low-signal conflicts.** `KEEP_THRESHOLD = 0.3`;
   a material conflict with no resolved country and a single actor took the
   penalties and was silently filtered out.
4. **GDELT had no retry** (unlike FIRMS/EONET) and its DOC fallback is slow and
   throttled — an intermittent total source failure.
5. **No way to tell *why*.** An empty Conflict layer looked identical whether the
   world was calm or the sources were down.

### The fixes

- **Rolling GDELT window.** `fetchBulkExport` now walks backwards through the
  newest file's 15-minute slots (`bulkExportUrls`, pure timestamp arithmetic on
  the filename — no extra index request), pulling a bounded set
  (`GDELT_MAX_FILES = 6`) with bounded concurrency (`mapPool`). A slot GDELT
  skipped simply fails and is tolerated; the fetch fails only if *every* slot
  does. `normalize` de-duplicates by `GLOBALEVENTID` first so overlapping slots
  cannot crowd out distinct events under the `GDELT_MAX_EVENTS` cap.
- **Persisted-event replay.** `runAssembly` now loads `queryEvents({hours})`
  after persisting the live clusters and merges the rows not already present,
  flagged `replayed`. These are real, within-window events observed in an
  earlier cycle; they are never re-persisted (no timestamp bump). This is what
  actually retains a 24h window when each cycle only sees ~15 minutes.
- **Material-conflict floor.** `scoreRelevance` floors a material conflict
  (`quadClass === 4` or `goldstein <= -5`) at `KEEP_THRESHOLD`, with the reason
  `material conflict (floored)`. A floor cannot manufacture signal — it only
  stops a real one from being filtered out.
- **GDELT retry.** One bounded transient retry, mirroring `firms.ts`/`eonet.ts`.
- **`coverage.ts`** — a pure report (`observed | quiet | degraded |
  unavailable`) that reads only the assembled state and explains an empty
  Conflict layer: an honest quiet zero, a source coverage gap, or no feed at all.
  Tests pin all four states.

### Where it surfaces

The dossier shows a `retained` badge on a replayed event, the map footer shows a
`N retained` count, and when no conflicts are plotted an amber line under the map
states which of the three situations applies. An empty conflict layer can no
longer read as proof of calm.

### Shared Evidence & Research Engine in the dossier (Phase 4, event level)

The event dossier now has an **Evidence & Research (engine)** section
(`components/investor-eye/event-research.tsx`) that drives the SAME Python
web-research engine behind the Research screen and the company brief, through the
existing `/api/research/*` front door (`use-event-research.ts`). It is LAZY — an
event does not auto-start a multi-minute run on open — and cached per event.
Findings are the engine's: it renders sources, claims (with verification status),
citations and a conflict count, plus the run's deterministic `answer`; with no
runtime it says so (`npm run setup:python`) rather than faking a brief. The
mandate text is built by a pure, tested `research-question.ts` so what the engine
searches for is reviewable.

This is also the concrete "use AI to find the conflict" path: ask the engine to
**corroborate** a conflict the structured feed only hinted at, and it returns
cited evidence rather than a generated narrative.

### What is NOT yet done (honest)

- **Map-level AI conflict backfill:** the above produces *cited evidence inside a
  dossier*. Promoting engine findings into first-class **map events**
  (`AI-INTERPRETED`) — so a thin Conflict layer can be filled from research — is
  not wired; that needs a provenance contract for AI-derived events and an
  explicit confidence/identity policy.
- **ReliefWeb** (a natural conflict source) was evaluated and REJECTED as a
  zero-config source: its API moved to v2 and from 1 Nov 2025 requires a
  pre-approved `appname`. It would have to ship as an optional, operator-
  configured source — not a default.
- **Python-native world tools** (e.g. `world_conflicts`, `event_evidence` in the
  authoritative Python registry) are not added; Investor Eye's agent tools remain
  the TypeScript `investor-eye-tools.ts` set, and the dossier reaches the engine
  directly. Wiring domain tools into the Python registry needs a JDdS data-bridge
  route for `GeopoliticalEvent`.

---

## 5r. Phase 20 — AI conflict search, and world events on the Python tool registry

Two completions of the Phase 2/4 work.

### "Find conflicts with AI" (`conflict-research-panel.tsx`)

When the structured feed's conflict coverage is thin — or the user simply wants
independent corroboration — the analysis row now carries a **Conflict research
(AI, cited)** panel. It asks the shared Evidence & Research Engine for a conflict
situation report over the current window and renders the engine's findings
(sources, claims with verification status, contradictions) via the shared
`research-findings.tsx` presentation.

It deliberately does **not** create map pins. Turning an LLM finding into a
plotted event needs a provenance/identity policy we will not fake, so the panel
gives exactly what the engine can defend and labels it as research. The mandate
(`windowConflictQuestion`) is pure and tested, and forbids invented events.

### World events on the Python tool registry (`get_world_events`)

The authoritative agent runtime is Python, but it had no access to Investor Eye's
`GeopoliticalEvent` feed. Added, following the established finance-tool pattern:

- **`world_events` JDdS bridge capability** — a new read-only capability in its
  own module (`src/lib/harness/world-events.ts`, extracted so the ratcheted
  `data-bridge.ts` does not grow). It reads normalized events with window/type/
  severity/country/text filters or a single event by id, ranked by relevance then
  recency, and copies the `rowToEvent` field shapes.
- **`get_world_events` Python tool** (`python/harness/world_tools.py`, registered
  in `service.py`) — the honesty contract mirrors the finance tools: an
  unreadable store is a `source_failure`, never "no events happened"; an empty
  result is a no-match over a *filtered* feed, explicitly not proof the world was
  calm.

---

## 5s. Phase 21 — the full event dossier, and actionable AI setup

Two experience fixes from real use.

### Clicking an event opens a real dossier

The dossier previously lived only in the narrow right rail (a long document in
~360px), and in full-page map mode in a `max-w-sm` bottom sheet. Selection now
has two levels:

- **Rail peek** — single click still shows the compact panel beside the map.
- **Full dossier** — an **"Open dossier"** button in the header (or double-click
  the panel) opens `event-dossier-overlay.tsx`: a wide, centred, **two-column**
  overlay (`EventPanel wide`, using the same CSS-columns packing as the standing
  panels), portaled to `document.body` like `FullPageMap`, dismissed with
  **Esc** (the screen's Escape/j-k handlers stand down while it is open), a
  backdrop click, or **Back to map**. `store.dossierOpen` is view state,
  deliberately not persisted.

### "AI not configured" is actionable, not a dead end

The Analyst and the Evidence/Conflict-research panels used to print
"no AI provider is configured" with no way forward. They now show **Open AI
settings**, which deep-links to the exact section: a new SSR-safe helper
(`navigation.ts`) dispatches `be:navigate { tab: 'settings', section: 'ai' }`,
and the shell's handler opens the **Settings modal at that section** (settings is
a modal, not a tab). The research-engine panels distinguish "needs the Python
runtime" (`npm run setup:python` — stated, not deep-linkable) from "needs
provider configuration" (deep-linked).

### The rail was unreadable — widened and enlarged

User feedback: the right rail was 360px with 8–10px type, so a clicked event or
country was very hard to read. Fixed: rail **440px (lg) / 460px (xl)**, hero
**62vh**; the Live Event Stream and Country panel now use **11–13px** type,
larger severity markers, more row padding and **3-line** titles; the dossier
`Block`/`Row` primitives went 9–10px → 11–12px. The rail's panel **precedence is
company → event → country → market**, so clicking a conflict always shows the
event dossier rather than a stale country panel. Presentation only.

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
| AIS / ADS-B / OpenStreetMap / CelesTrak / Natural Earth as live layers | Each is key-gated, restricted, or a bulk dataset with no sensible live cadence | **Not wired.** The adapter contract makes each one connector + normalizer + registry entry + catalog entry when a legally usable source is chosen. Natural Earth already ships as the map geometry (`public/geo/world.geo.json`). |
