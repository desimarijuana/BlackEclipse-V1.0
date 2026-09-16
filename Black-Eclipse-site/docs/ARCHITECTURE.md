---
title: Architecture
status: Current
last-verified: 2026-09-15
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

## Layer 1 — Screens & components

```
src/components/
  screens/        full-page views + their data/hook modules
  layout/         sidebar, top-bar, global-search, agentation
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
`economics` (+`snapshot`, `calendar`), `search` (+`global`, `index`), `agent`
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
| Investor Eye | `Country`, `GeopoliticalEvent`, `EventEntity`, `Relationship`, `SourceRun` |
| Trading journal | `JournalProfile`, `TradingAccount`, `Strategy`, `StrategyRule`, `Setup`, `Tag`, `JournalDay`, `DailyReview`, `DailyEmotion`, `Trade`, `TradeExecution`, `TradeScreenshot`, `TradeAnnotation`, `TradeTag`, `MarketContext`, `JournalEntry`, `Review` |

Two design notes that matter:

- **Dedup by constraint.** `Asset` is unique on `[marketId, symbol]`; `Price` is
  keyed by `assetId`; `NewsItem` has a `dedupKey`. Imports are idempotent upserts,
  not inserts.
- **Auth-ready, not auth-ful.** The journal carries an optional owner concept so
  a `User` relation can be added later without a rewrite. There are no accounts
  today — the app is a guest app.

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
| Shape | sections → columns → widgets, + rail zone | panels with presets/ops |
| Persistence | `localStorage` via `use-workspace` | `localStorage` via `use-market-workspace` |

Both are real and both are supported. The **retired** thing is
`src/lib/customize/` — an earlier kernel that is documented as superseded and
must not receive new features. See ADR-005 and ADR-006.

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
SOURCE (GDELT, USGS, /api/indices, /api/economics + FRED CSV, JDDS Asset/Price)
  ↓ src/lib/investor-eye/sources/*     fetch via the shared connectors `safeGet`
RAW
  ↓ classify.ts / cluster.ts / dedup.ts / confidence.ts   (pure, unit-tested)
normalized + clustered events
  ↓ state.ts        assemble, cache (SWR), persist, provenance, SourceRun rows
JDDS (Country, GeopoliticalEvent, EventEntity, SourceRun) + in-memory cache
  ↓ /api/investor-eye/*  → DataHub topics (provenance envelope) → Zustand store
  ↓ layers.ts (pure builders) → MapLayer[] → <WorldMap> (ECharts)
```

| File | Owns |
|---|---|
| `types.ts` | `NormalizedEvent`, `EventSource`, `MapLayer`, `InvestorEyeState`, provenance |
| `countries.ts` | canonical country gazetteer (ISO codes, region, centroid, aliases, market link) |
| `classify.ts` | event type / severity / channels / commodities / sectors (pure) |
| `cluster.ts` | dedup clustering + internal data-quality confidence (pure) |
| `dedup.ts` | stable `dedupKey` for idempotent upserts |
| `geo.ts` | grid aggregation so dense events never render raw |
| `sources/` | `registry.ts` + `gdelt.ts` + `usgs.ts` (`EventSource` adapters) |
| `state.ts` | `assembleState`, market observations, country summaries, `SourceRun` bookkeeping |
| `phase2.ts` | real economic metrics (FRED CSV), companies (JDDS `Asset`), price history |
| `analytics.ts` | risk decomposition, exposure, transmissions, analogues, NL `planQuery` |
| `graph.ts` | pure edge → nodes/links aggregation (per-kind caps, honest truncation) |
| `graph-data.ts` | derives + persists `Relationship` / `EventEntity` / `Country`; `queryEdges` |
| `cameo.ts` | CAMEO root code → event type, Goldstein → severity, **FIPS 10-4 → ISO2** |
| `relevance.ts` | investor-relevance score (0..1) + reasons; the feed's display threshold |
| `sources/news.ts` | turns existing `NewsItem` rows into events (no new feed/credentials) |
| `history.ts` | candle backfill + coverage, reusing the alerts yfinance path |
| `layers.ts` | pure `MapLayer` builders (events, markets, conflict, energy, trade, weather, economy, companies, portfolio) |
| `map-echarts.ts` | the ONLY ECharts-aware module; layer → option + event bridge |
| `app-geo.ts` | loads/registers `public/geo/world.geo.json` |
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
extra feed. GDELT's FIPS country codes are mapped to ISO2 in `cameo.ts` — they
conflict with ISO for several important countries.

**Optional work never blocks the map.** The candle-history backfill (~170s
across 30 markets) is fire-and-forget inside `assembleState`; awaiting it
blocked the first world-state response and made the map show "0 events".

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
