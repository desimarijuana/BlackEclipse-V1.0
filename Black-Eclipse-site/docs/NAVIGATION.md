---
title: Navigation — Where Things Live
status: Current
last-verified: 2026-09-18
---

# Navigation — Where Things Live

**Who this is for:** anyone asking "which file do I open to change X?"

This doc is also the **update trigger table**: when you add, move, or rename a
top-level folder or a major module, update the relevant row here in the same
change. That is the mechanism that keeps docs from drifting.

## Top-level map

```
Black-Eclipse-site/
  src/
    app/            Next.js App Router: page.tsx + api/**/route.ts
    components/     UI — screens, layout, chat, ui primitives, workspaces
    lib/            All logic: data, scraper, agent, domains
    hooks/          Shared React hooks
    types/          Shared TypeScript types
    generated/      Prisma client output (gitignored — do not edit)
  prisma/           schema.prisma (the JDDS schema)
  scripts/          Importers, bridge, doctor, db-guard, QA
  skills/           The engineering operating system (ARCHITECT/REMEMBER/…)
  docs/             This folder
  jdds.db           SQLite data vault (committed as a seed snapshot)
```

## By task

| I want to… | Open |
|---|---|
| Change the app shell / add a tab | `src/components/screens/stock-chat.tsx`, `src/components/layout/sidebar.tsx` |
| Change sidebar defaults / shortcuts | `src/lib/sidebar/config.ts` |
| Add a language / translate UI chrome | `src/lib/i18n/` (`locales.ts` = registry + RTL, `dictionaries/en.ts` = canonical keys, `dictionaries/index.ts` = translations, `translate.ts` = lookup, `store.ts` = persisted choice + `<html lang/dir>`, `use-t.ts` = hook) |
| Add an accessibility option | `src/lib/i18n/store.ts` (`A11yPreferences` + document classes), `src/app/globals.css` (`a11y-*` rules), `src/components/screens/customization-settings.tsx` |
| Change UI sounds / add a cue / add a voice pack | `src/lib/sounds/` (`config.ts` = cues + `SOUND_PACKS` + asset path helper, `sound-manager.ts` = Howler singleton with per-source cache, `store.ts` = persisted prefs incl. pack + per-cue volume/mute/custom, `sound-provider.tsx` = delegated listener), assets `public/sounds/<pack>/<cue>.wav`, UI `src/components/screens/sound-settings.tsx`; opt in with `data-sound="…"` or `sound.*()` |
| Work on the screener | `src/components/screens/market-overview.tsx` (shell: state, fetches, filters), `use-screener-filters.ts` (pure filter/sort), `use-global-markets.ts` + `market-overview-global-markets.tsx` (Global Markets tab), `use-market-tabs.ts` (forex/commodities state), `market-stock-tables.tsx` / `market-fund-etf-tables.tsx` / `market-tables.tsx` (tables), `market-loaders.tsx` (table loaders); shared screener logic/types/placeholders live in `src/lib/screener/` (`data.ts`, `format.ts`) |
| Work on heatmaps / volume analytics | `src/lib/heatmap.ts` (turnover math + payload contract), `src/app/api/heatmap/route.ts`, `src/lib/dashboard/heatmap-widget.tsx`, `src/components/screens/volume-analytics.tsx` |
| Work on Market Bubbles | `src/components/screens/market-bubbles.tsx` (consumes `/api/heatmap?volume=1`) |
| Work on the Earnings calendar | `src/components/screens/earnings-calendar.tsx` (shared grid + day detail), embedded at the top of the Market Screener (`market-overview.tsx`, `earnings` section key) and as the `EarningsCalendarWidget` (`src/lib/dashboard/widgets.tsx`); `src/lib/earnings.ts` + `src/app/api/earnings/route.ts` (Alpha Vantage → Nasdaq). No standalone page |
| Work on Fundamentals | `src/lib/fundamentals/` (`types`=Eclipse schema, `providers/`=SEC/FMP/Yahoo, `normalize`, `compute`=metrics+risks, `format`), `src/components/screens/fundamentals/` (`panel.tsx`=presentational sections, `use-fundamentals.ts`=data hook), route `src/app/api/fundamentals/route.ts`; Yahoo bridge `scripts/yfinance_fundamentals.py`. Rendered ONLY as the Market Screener popup's **Fundamentals** tab (`src/components/screens/tradingview-chart.tsx`) — there is no standalone page |
| Add a fundamentals provider | One `FundamentalsProvider` file in `src/lib/fundamentals/providers/` + a line in `PROVIDER_ORDER` (`providers/index.ts`); add its key to `PROVIDER_KEYS` if it needs one |
| Work on portfolio | `src/components/screens/portfolio/`, `src/lib/portfolio/`, `src/hooks/use-portfolio-engine.ts` |
| Work on portfolio risk/correlation math | `src/lib/portfolio/matrix.ts` (date-aligned correlation + Euler risk decomposition), `src/lib/portfolio/risk.ts` |
| Work on portfolio widgets | `src/components/screens/portfolio/widgets.tsx` (registry + renderers), `use-fund-data.ts` (data bundle) |
| Work on the journal | `src/components/journal/`, `src/lib/journal/` |
| Journal date formatting | `src/lib/journal/dates.ts` — journal dates are UTC everywhere, so format month/day labels in UTC or they render a month off |
| Seed / clear journal demo data | `src/lib/journal/demo.ts` (generator + marker), `src/app/api/journal/demo/route.ts` (seed/clear), `scripts/seed-journal.ts` (CLI wrapper) |
| Work on the dashboard widgets | `src/lib/dashboard/`, `src/components/screens/dashboard/` |
| Work on Live Intelligence (live news streams) | `src/lib/dashboard/live-intelligence-widget.tsx` (player + states + channel manager), `live-channels.ts` (channel registry + embed/safety helpers), `live-intelligence-store.ts` (persisted selection), `live-resolver.ts` + `src/app/api/live-streams/route.ts` (server-side cached current-live-id resolver) |
| Add/edit a dashboard widget | `src/lib/dashboard/registry.tsx` + `widgets.tsx` (and `widget-def.ts` contract) |
| Work on the widget-grid engine | `src/lib/workspace/`, `src/components/workspace/` |
| Work on the agentic runtime (agents, tools, providers, events) | `python/harness/` (`agents.py`, `tools.py`, `models.py`, `graph.py`, `events.py`); architecture: `docs/harness/architecture.md` |
| Change an agent's system prompt / identity | `python/harness/prompts.py` (e.g. `ECLIPSE_AGENT_SYSTEM_PROMPT`), composed in `agents.py` — authoritative in Python |
| Add a harness tool / agent / model provider | `python/harness/finance_tools.py` (or a new `register_*`), `python/harness/agents.py`, `python/harness/models.py` (`PROVIDER_CATALOG`) — see `docs/harness/architecture.md` → Extension points |
| Work on hybrid financial retrieval / source selection | `python/harness/retrieval/` (`planner.py` = source selection, `layer.py` = orchestrator, `structured.py`/`web.py` = providers, `cache.py`, `parallel.py`, `validate.py`, `conflicts.py`, `aggregate.py`); tools in `python/harness/retrieval_tools.py` |
| Add/edit a retrieval data type or provider | `retrieval/contract.py` (`DataType`), `retrieval/planner.py` (`_PLAN`), `retrieval/policies.py` (freshness + TTL) — new provider implements `retrieval/sources.py` `RetrievalSource` |
| Change web search / page retrieval | `src/lib/web-research.ts` (the one shared implementation) + the `web_search`/`web_fetch` capabilities in `src/lib/harness/data-bridge.ts` |
| Give the retrieval layer a new data source | `src/lib/harness/data-bridge.ts` capability + `DataCapability` in `src/lib/harness/types.ts` + the route whitelist |
| Change the harness front door / API proxy | `src/lib/harness/` (`run-service.ts`, `python-client.ts`, `python-runtime.ts`), routes `src/app/api/harness/` |
| Work on live streaming (SSE) | `python/harness/{events,graph,main}.py` (`model.delta` + `/runs/{id}/stream`), `src/app/api/harness/runs/[id]/stream/route.ts`, `src/app/api/harness/chat/stream/route.ts`, `src/lib/agent/registry.ts` |
| Work on conversation checkpoints | `src/lib/chat/checkpoint-store.ts`, `src/app/api/chat/checkpoints/route.ts`, `src/components/chat/checkpoint-bar.tsx` |
| Work on the git workflow (commit/push) | `src/lib/git/service.ts`, `src/lib/git/client.ts`, `src/app/api/git/route.ts`, `src/components/screens/git-panel.tsx` (Settings › Git) |
| Work on chat session workspaces (attached docs, agent output folders) | `src/lib/chat/session-store.ts` (server fs), `session-types.ts`, `extract.ts`, `session-client.ts`; routes `src/app/api/chat/session/`; UI `src/components/chat/session-bar.tsx`; context injection `python/harness/graph.py` (`_user_message`) — see `docs/ARCHITECTURE.md` § Chat session workspaces |
| Work on token usage / analytics | capture in `python/harness/graph.py` (`_extract_usage`), columns + `usage_summary()` in `python/harness/persistence.py`, `GET /usage` in `main.py`; proxy `src/app/api/harness/usage/route.ts` + `getUsageSummaryFromRuntime`; UI `src/components/screens/analytics-settings.tsx` (Settings › Analytics) |
| Give a Python tool JDdS data | `src/lib/harness/data-bridge.ts` (capability) + `DataCapability` in `src/lib/harness/types.ts`; the Python tool calls `ctx.data_bridge.fetch(...)` |
| Work on instrument identity / symbol resolution | `src/lib/instrument-identity.ts` (`resolveInstrument`, `verifyProviderIdentity`), market/venue aliases in `src/lib/markets.ts` (`resolveMarketId`, `MARKET_EXCHANGE_ALIASES`); collision fixtures + tests `src/lib/instrument-collisions.json` / `.test.ts`; bridge resolution in `src/lib/harness/data-bridge.ts` |
| Change harness persistence / the agent-memory DB | `python/harness/persistence.py` — separate `agent-memory.db`, NOT `prisma/schema.prisma` |
| Install / repair the Python runtime | `python/requirements.txt`, `scripts/setup-python.js` (`npm run setup:python`), `scripts/doctor.js`, `scripts/test-python.js` |
| Work on the market-panel grid | `src/lib/market-workspace/`, `src/components/market-workspace/` |
| Work on Investor Eye (world-state globe) | `src/lib/investor-eye/`, `src/components/investor-eye/`; audit + contract: `docs/investor-eye-architecture.md` |
| Add an Investor Eye source (GDELT/USGS/…) | `src/lib/investor-eye/sources/` (`registry.ts` + one `EventSource` adapter) **and** a governance entry in `src/lib/investor-eye/source-catalog.ts` (a test fails without one) |
| Declare a source's licence / attribution | `src/lib/investor-eye/source-catalog.ts` (surfaced by `/api/investor-eye/health` → `source-health-panel.tsx`) |
| Resolve a coordinate to a country (no place text) | `src/lib/investor-eye/admin-boundaries.ts` (`countryAtPoint`/`boundaryAtPoint`, point-in-polygon over `public/geo/world.geo.json`); centroid fallback is in `sources/firms.ts` |
| Add an Investor Eye map layer | `src/lib/investor-eye/layers.ts` (`MapLayer` builder + `LAYER_META` colour/group/symbol) + `store.ts` `DEFAULT_LAYERS`. Domain layers match event TYPE **or** economic CHANNEL (`buildDomainLayer`) — never type alone |
| Change Investor Eye colours / layer groups / legend | `src/lib/investor-eye/layers.ts` (`LAYER_GROUPS`, `LayerMeta`, `SEVERITY_COLORS`) — consumed by the controller, timeline, map adapter and full-page dock |
| Work on the full-page "map only" mode | `src/components/investor-eye/full-page-map.tsx` (+ `store.fullPage`); reuses `WorldMap`/`EventPanel`, portaled to body |
| Work on the live event stream / conflict feed | `src/components/investor-eye/live-feed.tsx`; conflict RSS wires in `DEFAULT_NEWS_FEEDS` (`src/lib/settings.ts`) |
| Change the 3D globe surface or the 2D map geometry | `src/lib/investor-eye/app-geo.ts` (`worldGlobeTexture(skin)` draws the globe texture from `public/geo/world.geo.json` — `GLOBE_PALETTES` holds the blue `glow` and plain `black` surfaces; `ensureWorldMapRegistered()` for 2D) |
| Change the map look (globe rim, pin glow, starfield) | `src/lib/investor-eye/map-echarts.ts` (`PIN_SIZE`/`PIN_GLOW`, `GLOBE_CORE_SIZE`/`GLOBE_HALO_SIZE`, `GEO_BY_SKIN`, light/atmosphere/emission) + `src/components/investor-eye/starfield.tsx` |
| Add or fix a map marker SHAPE | `src/lib/investor-eye/layers.ts` (`SYMBOL_PATHS`). A cut-out must wind OPPOSITE to its outer shape (nonzero fill rule) and a circle must be TWO 180° arcs — see §5n of `investor-eye-architecture.md` |
| Change which projection / surface skin is offered | `src/components/investor-eye/map-view-controls.tsx` (the only place; rendered by the hero header AND the full-page dock) + `MAP_SKINS`/`mapSkin`/`showStars` in `store.ts` (the STARS toggle unmounts `starfield.tsx`) |
| Debug a stuck full-screen loader on a map tab | `src/components/investor-eye/world-map.tsx` — its loader must stay SCOPED; `TopLoader` portals to `document.body` and will cover the whole app |
| Work on event→market price reaction | `src/lib/investor-eye/reaction.ts` (pure measurement) + `src/app/api/investor-eye/reaction/route.ts` + `reaction-panel.tsx` |
| Add/edit event alert rules | `src/lib/investor-eye/alert-rules.ts` (predicates + presets) + `src/app/api/investor-eye/alerts/route.ts` + `alerts-panel.tsx` |
| Fix where an event is plotted (city/port) | `src/lib/investor-eye/places.ts` (curated gazetteer + `resolvePlace()`); used by `sources/news.ts` |
| Fix where a POLICY event is plotted (capital vs centroid) | `src/lib/investor-eye/geo-resolve.ts` (`resolveEventLocation`, `reResolveEventLocation`) + `CAPITALS` in `countries.ts`; hollow markers are styled in `map-echarts.ts` |
| Work on saved views | `src/components/investor-eye/saved-views.tsx` + `store.ts` (`saveView`/`applyView`) |
| Work on data-source health / governance | `src/app/api/investor-eye/health/route.ts` + `source-health-panel.tsx` (reads `SourceRun` rows, joins `source-catalog.ts`) |
| Fix events merging into nonsense clusters | `src/lib/investor-eye/cluster.ts` (`shouldCluster` + `clusterSignature`) and `dedup.ts` (`dedupKeyFor`); never let synthesized title text score similarity |
| Surface real article headlines on events | `src/lib/investor-eye/enrich.ts` (news-corpus URL join, ~1% hit rate) and `article-meta.ts` / `article-meta-fetch.ts` (reads `og:title` from the linked page — the effective path); route `src/app/api/investor-eye/article/route.ts` |
| Make provider-synthesized event titles readable | `formatEventTitle` in `src/lib/investor-eye/format.ts` (used by the dossier header + live feed) |
| Work on the event detail dossier | `src/components/investor-eye/event-panel.tsx` (What happened / Actors / Where & when / Detail / Observed / exposure / reaction / Sources / Timeline) |
| Work on "Explain this event" (AI analyst) | `src/lib/investor-eye/event-record.ts` (prompt + honesty rules), `explain-panel.tsx`, `src/app/api/investor-eye/explain/route.ts` |
| Work on situation recurrence ("4th incident this week") | `src/lib/investor-eye/situations.ts` (pure grouping by type+country), `situation-panel.tsx`, `src/app/api/investor-eye/situations/route.ts` |
| Work on the relationship graph | `src/lib/investor-eye/graph.ts` (pure builder) + `graph-data.ts` (edges/persistence) + `graph-panel.tsx` |
| Add an AI Analyst tool (Investor Eye) | `src/lib/agent/investor-eye-tools.ts` (spread into `TOOLS`) |
| Change scraping / scheduling | `src/lib/scraper/` (`scheduler.ts`, `price-scraper.ts`, `fetchers/`) |
| Change news ingestion | `src/lib/news/ingest.ts`, `src/app/api/news/` |
| Change economics/macro | `src/lib/economics/`, `src/components/screens/economics/` |
| Change alerts | `src/lib/alerts/`, `src/app/api/alerts/`, `src/app/alerts/` |
| Change the AI agent / research | `src/lib/agent/` (`registry.ts`, `loop.ts`, `research.ts`, `tools.ts`) |
| Work on the chat response lifecycle / streaming UI state | `src/lib/agent/` — `response-model.ts` (typed status/activity), `events.ts` (`normalizeHarnessEvent`), `use-agent-run.ts` (shared hook); UI `src/components/chat/response-status.tsx`, `chat-history.tsx`, `activity-feed.tsx` + `activity-item.tsx` (tool/retrieval steps); plan/audit `docs/chat-ui-audit.md` |
| Change the chart | `src/lib/chart/`, `src/components/chart/`, `src/components/screens/tradingview-chart.tsx` |
| Add/fix a chartable index | `src/lib/indices.ts` (registry + providers), `src/lib/scraper/fetchers/psx-index.ts` (non-Yahoo source); `HEATMAP_MARKETS` in `src/lib/heatmap.ts` for heatmap labels || Change global search (⌘K) | `src/lib/search/` (query grammar: `grammar.ts`; commands: `commands.ts`; calculator: `calc.ts`), `src/components/layout/global-search.tsx` |
| Change the header price ribbon | `src/components/layout/price-ribbon.tsx` (render + customization popover), `src/lib/ribbon/store.ts` (persisted symbol list, routing helpers); catalog symbols `src/lib/market-catalog.ts`; marquee styles `.price-ribbon`/`.price-ribbon-track` in `src/app/globals.css` |
| Add a palette sub-page / make a view reachable | `registerPage` in `src/lib/search/registry.ts` (`subroute`, `group`, `child`) + `useSubroute(<tab>, …)` in the screen; hook: `src/hooks/use-subroute.ts` |
| Add a symbol to the watchlist outside React | `addToWatchlist` in `src/lib/dashboard/watchlist-store.ts` |
| Create a price alert programmatically | `src/lib/alerts/quick-alert.ts` → `POST /api/alerts` |
| Change the Aurora glow | `src/components/ui/Aurora.tsx`, `src/lib/aurora-sentiment.ts`, `src/lib/aurora/` |
| Change app theming / branding / design tokens | `src/lib/theme/` (`tokens.ts` model + presets + `themeFromBrandColor` + `deriveThemeColors`, `store.ts` persisted overrides + user presets, `bridge.ts` chart sync/preview) → tabbed panel `src/components/screens/customization-settings.tsx` (embeds `aurora-settings.tsx` + `chart-settings.tsx`); chart palette store/preview `src/lib/chart-palette-store.ts`; token defaults in `src/app/globals.css` |
| Change API protection / rate limits | `src/lib/api-guard.ts` |
| Add a data provider / work on connectors | `src/lib/connectors/` (`catalog`, `types`, `registry`, `resolver`, `custom-rest`, `security`, `secrets`, `mapping`, `refresh`, `store`); settings UI `src/components/screens/data-sources-panel.tsx` |
| Add/change a provider API key | `src/lib/provider-keys.ts` (`PROVIDER_KEYS` registry + encrypted vault) → `/api/provider-keys` → `src/components/screens/api-keys-panel.tsx` (filtered by `categories` prop); LLM keys render under `settings.ai`, financial/data keys under `settings.investor-eye` |
| Change Settings information architecture / sections | `src/components/screens/settings.tsx` (`SectionId`, `NAV`), sub-pages in `src/lib/search/registry.ts` (`settings.*`) |
| Explain why a provider exists / which feature uses it | `src/lib/providers/directory.ts` (`providerMeta`, `INVESTOR_EYE_FEATURES`) → registry UI `src/components/screens/provider-registry-panel.tsx` |
| Test an LLM connection | `POST /api/agent/test` (real endpoint request) |
| Pull/ingest custom dataset records | `PUT /api/datasets` → `pullDataset` in `src/lib/connectors/refresh.ts` |
| Scheduled connector refresh | `src/lib/connectors/refresh-scheduler.ts` (started in `src/instrumentation.ts`) |
| Change the DB schema | `prisma/schema.prisma` → `prisma db push` |
| Change the DB client | `src/lib/db.ts` |
| Change boot behavior / start a worker | `src/instrumentation.ts` |
| Change styling / glass classes | `src/app/globals.css` (see the `black-eclipse-ui` skill) |
| Change boot diagnostics | `scripts/doctor.js`, `scripts/up.js` |
| Change DB durability/backup | `scripts/db-guard.js` |

## By domain folder (`src/lib/`)

| Folder | Owns |
|---|---|
| `agent/` | Provider abstraction, tool loop, multi-agent research, journal tools |
| `src/lib/harness/` | Harness **front door**: input validation, vault/agent resolution, Python-runtime client + launcher, read-only JDdS data bridge |
| `python/harness/` (repo root) | The **agentic runtime**: agents, tools, model providers, LangGraph loop, events, `agent-memory.db` persistence |
| `alerts/` | Condition evaluator, feeds, notifier, alert monitor |
| `aurora/` | Aurora palette store + theme |
| `theme/` | Centralized customization: `EclipseTheme` model + presets + brand-color generator + derived-color resolution + validation (`tokens.ts`), persisted zustand store + CSS-token injection + user presets w/ chart palette (`store.ts`), chart-palette bridge + preview (`bridge.ts`) |
| `chart/` | Chart types, data hooks, indicators, drawings, structure, providers |
| `connectors/` | Universal Data Connector Layer: provider catalog, capability resolver, custom REST connectors, SSRF/secret security, custom datasets, scheduled refresh |
| `provider-keys.ts` (`lib/`) | The API-key vault: registry of every operator credential + AES-GCM encrypted storage + env resolution/apply |
| `navigation-history.ts` (`lib/`) | Capped in-memory tab-visit stack (`recordVisit`/`backTarget`) backing `Alt+←`; framework-free, no React |
| `providers/` | Provider directory: purpose / used-by / tier metadata + the Investor Eye feature→provider map (client-safe) |
| `dashboard/` | Widget catalog/definitions, renderers, market views, intelligence, dashboard + portfolio stores |
| `i18n/` | Interface localization: locale registry + RTL, dictionaries, translator, persisted language/accessibility store |
| `economics/` | Macro fetching, sources, calendar, snapshot |
| `fundamentals/` | Investor financial-analysis tier: provider abstraction (SEC/FMP/Yahoo), Eclipse schema normalization, derived metrics + data-driven risks, JDDS cache — see `ARCHITECTURE.md` › Fundamentals |
| `investor-eye/` | World-state tier: event sources (GDELT/USGS/FIRMS/news), normalization/clustering, map layers, source governance catalog, geographic boundary lookup, risk/exposure/transmission analytics, ingestion + cache |
| `journal/` | Journal data access, trade math, analytics suite, CSV import |
| `market-workspace/` | The market-panel workspace engine |
| `news/` | Background RSS ingestion |
| `portfolio/` | Portfolio types + risk math |
| `scraper/` | Price/universe scraping, scheduler, fetchers, CSV |
| `search/` | Global search registry, intent, query grammar/operators, ranking, resolver, calculator/commands, stores |
| `screener/` | Market-screener shared logic: instrument record types + zero-valued demo/placeholder rows (`data.ts`), price/cap/time formatting (`format.ts`). Consumed by the screener UI **and** `/api/stocks` |
| `sidebar/` | Sidebar config + store |
| `sounds/` | Terminal-style UI audio feedback: cue catalogue, Howler manager, persisted pref store, delegated listener provider |
| `workspace/` | The widget workspace kernel (DataHub, ops, persistence, canvas) |

## By API route group

`stocks` · `quote` · `price-history` · `asset-details` · `symbols` ·
`markets`(+`global`) · `indices` · `forex` · `commodities` · `heatmap` ·
`earnings` (embedded calendar, no tab) · `news`(+`status`,`alert`) ·
`economics`(+`snapshot`,`calendar`) ·
`search`(+`global`,`index`) · `agent`(+`chat`,`research`,`activity`,`test`) ·
`journal/*` · `alerts/*` · `scraper`(+`import`) · `refresh` · `settings` ·
`cron`(+`run`,`refresh-news`) · `data-sources`(+`test`) · `datasets` ·
`data/[capability]` · `providers` · `provider-keys` · `fundamentals` ·
`harness/*` (runs, chat, models, agents, data, usage) ·
`investor-eye/*` (state, events, countries,
markets, layers, economy, companies, portfolio, risk, analogues, query, graph,
health).

## Key contracts (read before changing)

| Contract | File |
|---|---|
| Widget definition | `src/lib/workspace/widget-def.ts` |
| Widget registry (dashboard) | `src/lib/dashboard/registry.tsx` |
| DataHub topic/entry | `src/lib/workspace/data-hub.ts` |
| Connector contract | `src/lib/connectors/types.ts` |
| Fundamentals provider contract | `src/lib/fundamentals/types.ts` (`FundamentalsProvider`) |
| Fundamentals Eclipse schema | `src/lib/fundamentals/types.ts` (`FundamentalsSnapshot`, `FundamentalPeriod`, `FundamentalMetric`) |
| Investor Eye event-source contract | `src/lib/investor-eye/types.ts` (`EventSource`) |
| Investor Eye source-governance contract | `src/lib/investor-eye/source-catalog.ts` (`SourceCatalogEntry`) |
| Investor Eye map-layer contract | `src/lib/investor-eye/types.ts` (`MapLayer`) + `layers.ts` |
| Investor Eye relationship-graph contract | `src/lib/investor-eye/types.ts` (`RelationshipEdge`/`GraphNode`/`GraphLink`) |
| Investor Eye server cache | `src/lib/investor-eye/cache.ts` (globalThis-anchored, window-keyed) |
| Workspace layout ops | `src/lib/workspace/ops.ts` |
| Market workspace ops | `src/lib/market-workspace/ops.ts` |
| Agent provider interface | `src/lib/agent/types.ts` |
| Agent tool contract | `src/lib/agent/tools.ts` (`ToolDefinition`) |
| Harness front-door contracts | `src/lib/harness/types.ts` (proxy shapes + `DataCapability`) |
| Financial retrieval contract | `python/harness/retrieval/contract.py` (`FinancialRetrievalRequest`/`Result`, `NormalizedFinancialObject`, `EvidenceSet`) |
| Retrieval provider contract | `python/harness/retrieval/sources.py` (`RetrievalSource`, `SourceOutcome`) |
| Source-selection policy | `python/harness/retrieval/planner.py` (`_PLAN`) |
| Harness agent contract | `python/harness/agents.py` + `python/harness/schemas.py` (`AgentConfig`) |
| Harness agent system prompts | `python/harness/prompts.py` (authoritative; the TS side sends only an `agentId`) |
| Harness tool contract | `python/harness/tools.py` (`ToolDefinition`, `ToolRegistry`) |
| Harness model-provider contract | `python/harness/models.py` (`ProviderSpec`, `PROVIDER_CATALOG`) |
| Harness run persistence | `python/harness/persistence.py` (`agent-memory.db`) |
| Harness usage analytics | `src/lib/harness/types.ts` (`UsageSummary`), route `src/app/api/harness/usage/route.ts` |
| Streaming status labels | `src/lib/agent/registry.ts` (`statusFromEvent`) |
| Checkpoint wire shapes | `src/lib/chat/session-types.ts` (`Checkpoint`, `CheckpointSnapshot`) |
| Git service contracts | `src/lib/git/service.ts` (`GitStatus`, `GitFileChange`, `GitCommitInfo`) |
| Mutation guard | `src/lib/api-guard.ts` |
| Tab ids | `AppTab` in `src/components/layout/sidebar.tsx` |

## Documentation trigger table

When a change touches one of these, update the listed doc in the same change:

| Changed path | Update |
|---|---|
| `src/instrumentation.ts`, `src/lib/scraper/`, `src/lib/news/` | `DATA-FLOW.md` |
| `prisma/schema.prisma`, `src/lib/db.ts` | `ARCHITECTURE.md` (JDDS section), `DATA-FLOW.md` |
| `src/lib/workspace/`, `src/lib/market-workspace/`, `src/lib/customize/` | `ARCHITECTURE.md` (workspaces), `DECISIONS.md` |
| `src/lib/api-guard.ts`, auth/env behavior | `ARCHITECTURE.md`, `QUICKSTART.md` |
| `src/lib/connectors/`, `src/lib/provider-keys.ts`, `src/app/api/data-sources/`, `src/app/api/provider-keys/`, `src/app/api/data/`, `src/app/api/datasets/`, `src/app/api/providers/` | `ARCHITECTURE.md` (connector layer + operator credentials), `DATA-FLOW.md`, `DECISIONS.md` |
| `src/lib/investor-eye/`, `src/components/investor-eye/`, `src/app/api/investor-eye/` | `ARCHITECTURE.md` (Investor Eye), `investor-eye-architecture.md`, `DATA-FLOW.md`, `DECISIONS.md` |
| `src/lib/fundamentals/`, `src/components/screens/fundamentals/`, `src/app/api/fundamentals/`, `scripts/yfinance_fundamentals.py` | `ARCHITECTURE.md` (Fundamentals), `DATA-FLOW.md` |
| `src/lib/harness/`, `src/app/api/harness/`, `python/`, `scripts/setup-python.js`, `scripts/test-python.js` | `harness/architecture.md`, `harness/decisions.md`, `harness/phase-2-progress.md`, `DECISIONS.md`, `QUICKSTART.md` |
| `python/harness/retrieval/`, `python/harness/retrieval_tools.py`, `src/lib/web-research.ts` | `harness/architecture.md` (retrieval layer), `harness/phase-2-progress.md`, `ARCHITECTURE.md`, `DECISIONS.md` |
| `src/components/screens/stock-chat.tsx`, `src/lib/sidebar/config.ts` | `OVERVIEW.md`, `ARCHITECTURE.md` |
| Setup/scripts/`package.json` scripts | `QUICKSTART.md` |
| A new top-level folder or major module | this file |
| A new architectural decision | `DECISIONS.md` |

## Retired / do not build on

- `src/lib/customize/` — superseded customization kernel (ADR-005).
- The old JDdS daemon and its PostgreSQL provider system — removed.
- `MarketSidePanel` as a separate page — its widgets are now the workspace right
  zone (legacy name: "rail").
