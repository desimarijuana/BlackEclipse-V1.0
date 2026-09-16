---
title: Investor Eye — Architecture & Audit
status: Current
last-verified: 2026-09-15
---

# Investor Eye — Architecture & Audit

**Who this is for:** anyone implementing or extending Investor Eye (the
financial/geopolitical world-state surface). Read §1–2 for the audit, §3 for the
design, §4 for the Phase 1 build order, and §5 for Phase 2.

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

## 6. Conflicts with the spec, and how they were resolved

| Spec assumption | Repository reality | Resolution |
|---|---|---|
| Multi-route app (`/investor-eye`) | Single page + tab state machine, no screen router | Added an `investor-eye` **tab** (the repo's route convention). |
| `DataConnector` contract as specified | A different `DataConnector` already exists in `lib/connectors/types.ts` | Did **not** fork it; source adapters reuse `safeGet` and mirror its shape. |
| PostgreSQL / graph DB | SQLite-only JDDS; ADR-010 forbids casual new stores | Relational tables + JSON columns; documented as ADR-011. |
| Company/securities/country entities | `Asset.country` is a string; no `Country` model | Added `Country`; linked existing `Asset`/markets by ISO code without altering them. |
| Economic metrics for arbitrary countries | `ECON_SOURCES` exposes curated countries/indicators | Reuse it; show only what it can actually return, else `UNAVAILABLE`. |
| ACLED conflict data | Requires account/API auth | **Optional** — not wired; GDELT covers Phase 2 conflict so nothing breaks without it. |
