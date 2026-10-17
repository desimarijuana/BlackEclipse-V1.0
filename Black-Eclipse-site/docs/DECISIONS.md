---
title: Decisions (ADR log)
status: Current
last-verified: 2026-09-30
---

# Decisions — Architecture Decision Record

**Who this is for:** anyone about to re-litigate a choice, or wondering why
something is the way it is.

An ADR is a few lines recording *why* a significant decision was made — a commit
message for architecture. Write one when you make a meaningful choice. Keep it
short. Never delete an ADR; supersede it and mark the old one
`[SUPERSEDED by ADR-0XX]`.

> This is a readable mirror of the ADR section in
> [`../skills/ARCHITECT.md`](../skills/ARCHITECT.md). **That file is
> authoritative**; add new ADRs there first, then mirror them here.

---

## ADR-001 — Demo data + zero-config (2026)
**Decision:** Ship with demo data; no DB, no keys required to run.
**Why:** Zero-config policy + open-source friendliness.
**Impact:** All screens work immediately; real data is an opt-in. This is the
oldest and most load-bearing decision in the project.

## ADR-002 — RSS for news (2026)
**Decision:** Use free RSS feeds for news instead of a paid news API.
**Why:** No API key, no rate limits, open standard.
**Impact:** `/api/news` serves live news with an offline/mock fallback; ingestion
was later moved into JDDS (`NewsItem`) so requests do not re-fetch feeds.

## ADR-003 — Agent provider abstraction (2026)
**Decision:** Define an `AgentProvider` interface, default to the built-in mock,
and plug in real LLMs additively.
**Why:** Keeps chat functional with zero config while enabling real agents later.
**Impact:** The UI calls `getAgentProvider().chat(...)`. Adding a provider never
touches the UI.

## ADR-004 — Agentic scraper as the primary data source (2026)
**Decision:** The default market-data source is the free, built-in scraper; user
APIs are optional opt-ins; demo data is the fallback.
**Why:** Users should configure as little as possible.
**Impact:** Data-source priority is always scraper → user API → demo.

## ADR-005 — Workspace kernel supersedes `src/lib/customize/` (2026)
**Decision:** All page customization is driven by `src/lib/workspace/`
(sections → columns → widget cards, with relative column weights). Stored
layouts are validated and normalized on load; corrupt data falls back to
defaults **without overwriting** the stored payload. Pages get edit chrome
(drag/drop, add/remove, resize, templates) from the kernel only.
**Why:** The flat span model couldn't express free-form placement (multiple
widgets per column, individual widths). An earlier v3 "element model" in
`src/lib/customize/` was sketched but never shipped.
**Impact:** Adding a customizable page = a widget registry + the workspace
kernel. `src/lib/customize/` is **retired** — do not build on it.

## ADR-006 — Workspace stack: dnd-kit + Zustand + Immer (2026)
**Decision:** dnd-kit owns drag & drop; Zustand owns editor/layout/selection
state (one cached store per storage key); Immer owns layout mutations (every op
in `ops.ts` is a draft mutator applied via `produce`).
**Why:** Replaces hand-rolled pointer-drag DOM surgery, `useState` plumbing, and
manual structural clones. Ops become trivially testable.
**Impact:** New layout ops must follow the draft-mutator signature and get a unit
test. Persistence happens inside `commit()` — never call the save helper
elsewhere.

## ADR-007 — Page-header icon tiles (2026)
**Decision:** Every page header uses the portfolio-style icon tile: a 56px
rounded container (`border-primary/25 bg-primary/15`) wrapping a 30px
primary-colored lucide icon.
**Why:** Bare inline icons looked inconsistent next to the portfolio header.
**Impact:** New screens copy the tile; do not revert to bare small icons.

## ADR-008 — Two-click placement confirm (2026)
**Decision:** Widget placement is **preview-then-confirm**, not drop-to-commit.
Grab a card (click or drag-release), hover to preview the labeled ghost slot,
then click again (or the ghost/Confirm) to commit. **Escape or right-click
cancels** at any point.
**Why:** Drop-to-commit was unreliable across devices (touch pan gestures,
scroll-adjusted deltas, off-screen targets) and gave no chance to verify.
**Impact:** The drop target is projected from the **real pointer**
(`pointermove` + `elementFromPoint`), not dnd-kit's delta. Any new interaction
must respect the two-click contract.

## ADR-009 — Central command palette + query grammar (2026)
**Decision:** Global search (⌘K) is one command palette over `src/lib/search/`
built as two **pure, framework-free** steps: a **grammar** (`grammar.ts`) that
parses scopes (`>` `#` `@` `/` `~` `?`) and field operators (`kind:`, `class:`,
`market:`, `symbol:`), then a **resolver** (`resolver.ts`) that classifies intent,
scores the static registry + FlexSearch universe, and returns a `ResolvedSearch`.
The palette dispatches a **`Destination`** on a bus (`pendingDestination`) rather
than navigating directly.
**Why:** The command-center vocabulary is a user-facing contract that must grow
without touching the UI, and the query path must stay fully offline and
deterministic (no LLM on the query path — only an explicit "Ask AI" row).
**Impact:** Extending scopes/operators means editing `grammar.ts` and its tests
together. Ranking stays pure; personalization (visit history), pins, and collapse
state live in the Zustand command store. `calc.ts`/`commands.ts` add an offline
calculator and parameterized-command autocomplete (`alert`/`watch`/`chart` +
symbol); the palette renders no static command launcher. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "The command center".

## ADR-010 — Universal Data Connector Layer (2026)
**Decision:** Add a capability-addressed connector tier under
`src/lib/connectors/` that sits **after** the existing scraper chain and before
route-level demo fallbacks. Consumers ask for a *capability* (`PRICE`), never a
provider; a deterministic resolver picks the connector. Built-in connectors
outrank operator-configured ones; there is **no** automatic cross-provider
fallback (that would change provider semantics and needs its own ADR). Custom
API data lands in dedicated `CustomDataset*` tables and can never write to
`Asset`/`Price`/`Candles`; canonical writes stay an explicit, deferred operator
action.
**Why:** Operators need to bring their own data API without a rewrite per
provider, while ADR-004's `scraper → user API → demo` precedence and the
"never fabricate, never overwrite provenance" rules stay intact. The documented
"user API" tier had **no generic implementation** before this — this ADR adds
it rather than migrating an existing one.
**Impact:** `DataSource` gained `CUSTOM` and topics may return a provenance
envelope (`{ data, source }`); DataHub internals are unchanged otherwise.
Connector credentials use AES-256-GCM with an auto-generated local key
(`.connector-key`, gitignored) or `CONNECTOR_SECRET_KEY` on hosted deploys.
Custom connectors are GET-only and go through a hardened outbound path
(DNS-validated + pinned lookup, no redirects, 5 MB streamed cap, ≤10s timeout).
**Agent access (added later):** read-only `list_datasets` / `describe_dataset` /
`query_dataset` tools in `src/lib/agent/dataset-tools.ts`, spread into `TOOLS`;
every result states provenance. **Scheduled refresh + multi-value pull (added
later):** a dataset parameter may be a comma-separated list expanded into one
request per value, capped at `MAX_VALUES_PER_PULL = 25` with the overflow
reported; `refreshEnabled` datasets re-pull on the `dataset_refresh` cron, which
yields to the scraper's whole-market jobs rather than competing for the
synchronous SQLite write path. **Provider catalog (added later):** the Data
Sources screen shows a browsable catalog grouped by purpose (AI, economics,
market, crypto, custom); economics entries are derived from `ECON_SOURCES` so it
cannot drift, status is computed from the real environment, and the UI never
claims to have saved a key it cannot save (env-gated providers route to the
screen that sets them). Deferred: webhooks, POST bodies, pagination
(beyond value lists), OAuth, `~` dataset search, AI connector generation. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "The Universal Data Connector Layer".

## ADR-011 — Investor Eye is a separate event/intelligence tier, reused not forked (2026)
**Decision:** Investor Eye ("God's Eye") is built as a new **event + world-state
tier** under `src/lib/investor-eye/`, **not** as another connector capability and
**not** as a second market/portfolio/news stack. It:
1. registers its own `EventSource` adapters (GDELT, USGS) instead of forking the
   existing `DataConnector` contract, but reuses its hardened `safeGet` transport;
2. persists only **additive** JDDS models (`Country`, `GeopoliticalEvent`,
   `EventEntity`, `Relationship`, `SourceRun`) — **no graph database**, no
   Redis, no microservice. The relationship graph (spec §41) is a relational
   `Relationship` edge table aggregated into nodes/links by a pure builder;
3. visualizes through a provider-agnostic `MapLayer` abstraction rendered by
   ECharts (already a dependency), so the visualization can be swapped later
   without touching the data layer;
4. sources market observations from the **existing** `/api/indices` path
   (`IndexQuote` + the yfinance bridge) and portfolio exposure from the
   **existing** `use-portfolio-engine`, never duplicating them;
5. keeps the query path fully deterministic (keyword + gazetteer NL search, no
   LLM), matching ADR-009. AI is a separate, opt-in **AI Analyst** layer of
   read-only agent tools that query the structured data — never on the query
   path and never the source of a fact.
6. shares ONE globalThis-anchored, per-window cache across route bundles, so a
   fan-out of endpoints triggers a single source ingestion rather than one each.
**Why:** The repository is a single-page, SQLite-backed SPA with no geo/map
infrastructure and no geopolitical-event model. Building the smallest robust
foundation that reuses existing services avoids the duplicate-architecture and
over-build traps the specification explicitly warns against.
**Impact:** A new `investor-eye` tab; `country-fill`/`scatter`/`effect-scatter`/
`lines`/`heatmap` layer types (extensible via `registerLayer()`); honest
provenance (`LIVE`/`CACHED`/`HISTORICAL`/`UNAVAILABLE`). A failed source is
`UNAVAILABLE`, never a fake zero; the page and map still load on partial source
failure. Optional authenticated sources (e.g. ACLED) are supported but never
required. See [`investor-eye-architecture.md`](./investor-eye-architecture.md).

## ADR-012 — Data-source governance is its own registry, enforced by test (2026)
**Decision:** Every external source Investor Eye consumes must have an entry in
`src/lib/investor-eye/source-catalog.ts` (provider, licence, licence/terms URL,
commercial-use status, API-key requirement, attribution, rate limit, expected
freshness) — kept **separate from the `EventSource` adapter**, and enforced by
`source-catalog.test.ts`, which fails if a registered adapter has no entry, if an
entry has no registered adapter, or if `requiresApiKey` disagrees with the
adapter's `requiresCredentials`.
**Why:** "Public API" does not mean "free for commercial use". Fusing governance
into the adapters would make a licence question answerable only by constructing a
fetcher, and would let a new source ship with no licence declared and nobody
notice. A test is the only mechanism that keeps the registry complete as sources
are added.
**Impact:** A new source is now *connector + normalizer + registry entry +
catalog entry*, with the third and fourth held in sync mechanically.
`/api/investor-eye/health` joins the catalogue onto `SourceRun` accounting and
returns the required attribution lines; `SourceHealthPanel` renders them and
flags a runnable-but-undeclared source as a governance gap. Local data the app
produces itself (the stored RSS corpus) is marked `local: true` and exempt from
the licence-link requirement, since its upstream feeds declare their own terms.
AIS/ADS-B/OpenStreetMap/CelesTrak are deliberately **not** wired: each is
key-gated, restricted, or a bulk dataset with no sensible live cadence. Adding
one is connector + normalizer + registry + catalog entry, and nothing else
changes. See [`investor-eye-architecture.md`](./investor-eye-architecture.md) §5k.

---

## ADR-013 — Operator API keys are an encrypted vault layered over env vars (2026)
**Decision:** Credentials entered in Settings → API Keys are stored
AES-256-GCM-encrypted in `SystemConfig` via the existing `connectors/secrets`
path, declared once in `PROVIDER_KEYS` (`src/lib/provider-keys.ts`), and resolved
**env var first, vault second**. `applyStoredKeysToEnv()` copies stored keys into
`process.env` at boot so every existing consumer keeps reading env vars with no
per-provider refactor. A real environment variable is never overwritten, and
removing a stored key only clears a variable this process itself populated.
**Why:** Environment variables are right for a deployment but useless to a
zero-config local install — the user would have to edit a file and restart. The
repo also had no single place to enter a credential: the connector wizard only
accepts an arbitrary REST endpoint, so a user could not plug in, say, a Finnhub
key at all. Layering the vault over env vars preserves both: local convenience
and deployment authority, with one resolution order.
**Impact:** The key VALUE never crosses the API boundary — the browser sees only
`stored`, `fromEnv` and a masked hint. "Test" performs a real request and reports
the real status code (an invalid key returns 401, verified), never a success
inferred from the key existing. Adding a provider is one entry in `PROVIDER_KEYS`.
Secrets must never be logged and never returned; `SystemConfig` plaintext storage
is explicitly not used for them. See [`ARCHITECTURE.md`](./ARCHITECTURE.md)
(operator credentials) and [`investor-eye-architecture.md`](./investor-eye-architecture.md) §5l.

---

## ADR-014 — Map-local loading states must never portal to the body (2026)
**Decision:** A loading/empty overlay that belongs to a *region* of the app
renders inside that region. `TopLoader` (the app-wide transition loader) is
reserved for whole-screen loads and must never be used inside a card, panel, or
widget. `WorldMap`'s loading state is now a scoped inline overlay, and globe
initialisation has a hard 20 s ceiling that falls back to the flat map.
**Why:** `TopLoader` portals to `document.body` at `z-[45]`, so using it for a
component-level state silently promoted a map-local spinner to a full-app
blocker. The symptom was severe and confusing — the entire application, sidebar
included, sat on a frozen `95%` overlay — and it only appeared once the globe
path could take seconds to initialise. A component must not be able to assert
global UI state as a side effect of its own data loading.
**Impact:** The rule applies to any future region-scoped loader. The related
lesson is that this was invisible to `tsc` and to the flat map, so the globe
contract is now covered by a test (`map-echarts.test.ts`: the halo series must
exist, must be `silent`, and the core must be lightened toward white — the
dark-donut regression). See [`investor-eye-architecture.md`](./investor-eye-architecture.md) §5m.

---

## ADR-015 — Media widgets tear down their own player when not visible (2026)
**Decision:** A widget that plays media (live video/audio) must not rely on the
shell to stop it. The keep-alive tab model keeps every visited screen MOUNTED and
hides the inactive ones with `display:none`, and `WidgetDefinition.lazy` is
declared but never read — so an embed left mounted keeps streaming in the
background. The Live Intelligence widget therefore owns its teardown: an
`IntersectionObserver` on its root (which reports zero intersection inside a
`display:none` ancestor, and for a scrolled-off card) plus a `visibilitychange`
listener (the browser tab) unmount the iframe. Playback re-mounts with a fresh
embed URL when the card becomes visible again.
**Why:** Nothing in the repo tore an embed down on visibility — `TradingViewChartWidget`
leaves its iframe live under `display:none` — so a "Live TV" widget would have
burned bandwidth and CPU indefinitely on an unwatched tab. The two observers are
needed together: `visibilitychange` does not fire for in-app tab switches, and
the observer does not fire for OS-level tab switches.
**Impact:** Applies to any future media widget (video, audio, streaming, WebGL
animation). `lazy` remains dead — do not treat it as a teardown mechanism. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "Live Intelligence".

## ADR-016 — Track board replaces the row-band layout grammar (2026)
**Decision:** The widget workspace's default arrangement is a **masonry track
board**. A section's columns are vertical tracks; a pure packer
(`src/lib/workspace/pack.ts`, `rebalanceColumns`) distributes each section's
cards into the shortest track by estimated height. Every placement sizes to
content (`height: null`) with an intrinsic floor (`WidgetPlacement.minHeight`,
from `WidgetDefinition.minHeight` / the composition's `WIDGET_MIN_HEIGHT`).
`WorkspaceLayout.version` is `2`; `buildMarketViewLayout`/`composeBoard` replace
`composeRows`; the retired `HEIGHTS` band constants, `LayoutRow` and the
`items-start` row renderer are gone.
**Why:** The row-band grammar was structurally gappy. A section was a rigid
full-width row of content-height columns (`items-start`), so any short widget
left dead space beside a tall sibling, and the side rails (a 300px Watchlist and
4×190px tiles) left ~490px blank under the Watchlist. Pinned `HEIGHTS` were too
coarse for real content, so cards either clipped or left empty tails. "Widgets do
not fit properly / big gaps" was the symptom; rigid rows were the cause.
**Impact:** Packing runs at **compose time only** (defaults, templates, imports)
— never inside the store's `commit`, because masonry has no stable fixed point
for equal-height cards and re-packing on edit would silently reshuffle what the
user just dropped. Storage reset to **v7** dashboards / **v3** funds /
`be_dashboards_index_v7`; old layouts are not migrated (the band grammar cannot
be meaningfully carried forward). The 4-track engine capability remains for user
drag/drop. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) → "Dashboard layout grammar
(personas + track board)".

## ADR-017 — Frame vs grow card sizing and resizable side panels (2026)
**Decision:** Every track-board placement carries EITHER a **frame**
(`WidgetPlacement.defaultHeight`) — a definite box whose body stretches to fill
(charts, maps, live video, scrollable tables/feeds) — OR a **grow floor**
(`minHeight`) under content that sizes itself (compact tiles). The renderer keys
its body class off `isDefiniteCard(placement)`. Side zones get a
user-resizable width (`WorkspaceLayout.zoneWidths`, `ops.setZoneWidth`,
clamped 180–520px via a drag handle).
**Why:** The single `minHeight` field collapsed widgets: a grow card got a
`min-h` frame but the body used `flex-1`/`flex-basis:0`, so content with no
intrinsic height (a chart, a scrollable list) rendered at zero height and
looked broken. Splitting definite-frame widgets from growing tiles is what makes
them render. Fixed side-zone widths also wasted space — a user reading a long
watchlist wanted a wider panel.
**Impact:** `WidgetPlacement.defaultHeight` added and preserved by
`normalizeLayout`; `WIDGET_FRAME_HEIGHT` / `WidgetDefinition.defaultHeight`
added alongside `WIDGET_MIN_HEIGHT` / `minHeight`. Personas were redesigned into
nine genuinely different band shapes and renamed. Frame/grow confusion is the
first thing to check when a widget renders empty. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "Dashboard layout grammar (personas +
track board)".

## ADR-018 — Agentic runtime is Python (LangChain + LangGraph); separate agent-memory DB (2026)
**Decision:** The agentic harness runtime is **Python** — FastAPI + LangChain +
LangGraph in `python/harness/` — owning agents, tools, model providers, harness
events and run persistence. Next.js (`src/lib/harness/`, `src/app/api/harness/`)
is a thin front door: it validates input, resolves the agent preset + LLM config
from the settings vault, assigns the run id, and proxies to the runtime. It also
serves a guarded, read-only JDdS **data bridge** for the Python tools. Run state
and agent memory/skills live in a **separate SQLite database**
(`agent-memory.db`), not JDdS.
**Why:** The requirement was that the agentic side not be written in TypeScript,
and that it connect every model. Python is where the LangChain/LangGraph
ecosystem and provider integrations live, making "all models" and agent
authoring configuration rather than bespoke TS adapters. The vault and Prisma
are the two things Python cannot own, which is exactly why the front door keeps
those two jobs. A separate DB keeps high-churn operational state off the
committed JDdS snapshot.
**Impact:** Agent runs require the Python stack (installed by `postinstall` /
`doctor.js`); without it runs return 503 — never a fake agent. Universal model
coverage is a provider catalog plus the OpenAI-compatible protocol. The earlier
TypeScript Phase-1 kernel was retired. See
[`harness/architecture.md`](./harness/architecture.md) and
[`harness/decisions.md`](./harness/decisions.md) (ADR-H1…H12).

---

## ADR-019 — Provider-agnostic financial retrieval layer; web research is first-class (2026)
**Decision:** The agent requests an **objective + data type**, not a provider. A
dedicated `python/harness/retrieval/` package (`FinancialRetrievalLayer`) plans
the source(s) with a deterministic, explainable planner, retrieves them
(cache-aware, possibly in parallel), normalizes to one
`NormalizedFinancialObject`, validates, resolves source conflicts, and returns
provenance-carrying evidence. Tools call the layer; the layer is the only place
that knows JDdS, yfinance or the web exist. Web research
(`src/lib/web-research.ts`, the single shared search+fetch implementation) is a
first-class selectable path, not merely a fallback. A precise quantitative
request (historical prices, macro series, derived metrics) **never** uses web:
with no structured dataset the layer returns `UNAVAILABLE`.
**Why:** The Phase-2 objective is "what information do I need → what is the best
source → structured/cache/web/multiple → is the evidence fresh and reliable?" —
a decision that belongs in one explainable place, not scattered across tools.
It keeps the agent decoupled from every individual data source and keeps JDdS and
yfinance as *sources*, not mandates.
**Impact:** Adding a provider means implementing the `RetrievalSource` contract
and adding its name to the planner; source-selection policy is data. The
retrieval cache is in-process and shared across runs with in-flight
deduplication (no new database). See
[`harness/architecture.md`](./harness/architecture.md) and
[`harness/decisions.md`](./harness/decisions.md) (ADR-H10…H12).

---

## ADR-020 — A ticker is not an instrument identity; unhonoured qualifiers fail loudly (2026)
**Decision:** Instrument resolution requires a **canonical identity** —
`{ market, symbol, currency (ISO 4217), assetClass }` — not a bare ticker. Every
instrument resolution and payload carries it. A market qualifier (venue, country,
market id) is resolved through a single alias table (`resolveMarketId`); if it
cannot be honored the request **fails** (`market_unknown`). A bare ticker that
maps to more than one instrument is **`AMBIGUOUS`**, never a "best match". A
provider answer whose currency/market disagrees with the resolved identity is
**discarded**. `AMBIGUOUS` and `UNAVAILABLE` are correct, first-class outcomes.
**Why:** A live analysis of `FFC` (Fauji Fertilizer, PSX) returned a US
closed-end fund's price, stamped `realtime`, because the live path dropped the
`market` qualifier and fetched the bare ticker. Tickers are reused across venues,
asset classes and issuers (4160 colliding tickers in the committed master alone)
and carry no currency — a confidently wrong number is worse than no number.
**Impact:** `src/lib/instrument-identity.ts` owns resolution and returns a typed
failure union; the read-only bridge returns `AMBIGUOUS`/`UNAVAILABLE`; the Python
retrieval contract gains `AMBIGUOUS` + `InstrumentIdentity`; the fetchers refuse
an unresolvable market rather than emitting a bare US ticker. Every real
collision is a permanent regression fixture
(`src/lib/instrument-collisions.json`, generated from the master). Supersedes any
implicit "symbol is enough" assumption in the retrieval layer (ADR-019).

---

## ADR-021 — One failure contract, declared coverage, and terms-aware identity (2026)
**Decision:** Every tool and source reports failure through one taxonomy
(`src/lib/harness/failure.ts`): `ambiguous`, `market_unknown`, `not_found`,
`currency_mismatch`, `venue_mismatch`, `terms_missing`, `not_covered`,
`no_data`, `source_failure`, `incomplete`, `conflict`, `invalid_request`.
Message text is derived from the class, never hand-written per tool. Coverage is
**declared data** (`src/lib/harness/coverage.ts`), queryable via a `coverage`
capability — an unregistered market/asset class returns `not_covered` instead of
routing to a guessed backend. Derivatives and fixed income require contract
terms (`expiry`/`strike`/`right`, `maturity`/`coupon`/`seniority`) before a
value may be returned. Every numeric payload carries `currency` and `units`.
`get_news` falls through from the vault to the shared web transport and never
phrases a source failure as "no news". Source health is derived from recorded
runs (`healthy`/`degraded`/`failing`/`unknown`), so confidence is earned.
**Why:** The same underlying miss behaved differently across tools
(`get_market_snapshot` refused; `market_get_quote` returned a US fund;
`get_news` reported "no news" on an infrastructure miss). A false "no news" in a
financial tool reads as "nothing happened" — materially misleading. Uniformity
is the only way one tool's safety guarantee holds for all of them.
**Impact:** Extends ADR-020 (identity). Tools route through the shared classes;
a new asset class/venue is a data change in `coverage.ts`. `isCovered()` gates a
request before any source is attempted.

---

## ADR-022 — Deterministic retrieval, strict macro identity, and top-level degradation (2026)
**Decision:** Four rules complete the identity contract. (1) **D1 — parse once,
persist, replay.** A successful retrieval is written to `RetrievalRecord`
(`agent-memory.db`) keyed by request; an identical, non-realtime request replays
the stored result, so the same question yields identical figures and citations
instead of re-scraping (which drifts). (2) **A8 — macro series are identities.**
`python/harness/macro_identity.py` + `src/lib/harness/macro-identity.ts` resolve a
series to geography + institution + measure + adjustment + frequency. A generic
measure (`POLICY_RATE`) without a geography is AMBIGUOUS and never defaults to
US; non-US series route to non-US sources. (3) **D2 — truncation is withheld.**
A partial numeric parse (`1,23` from `1,234.56`) is detected and the result is
UNAVAILABLE + `incomplete`, never a figure. (4) **D3 — degradation is
top-level.** `degraded`/`degradation`/`incomplete`/`conflicts`/
`provenanceVerified` are fields on the result itself, not nested metadata, so a
value whose identity was not verified is structurally flagged.
**Why:** The same infrastructure produced drifting fundamentals (read-time
scrapes), conflicting policy-rate values (measure collision), a truncated figure,
and a wrong instrument — each invisible to the consumer because degradation was
either absent or buried.
**Impact:** Extends ADR-020/021. `RetrievalRecord` is idempotent (upsert on key).
Realtime data types are excluded from durable replay by design.

---

## ADR-023 — One shared resolution layer for every tool; no country/venue/asset-class default (2026)
**Decision:** Instrument resolution is unified in a single bridge resolver
(`resolveVaultInstrument` / `resolveAnyInstrument`), and **every** resolving
capability (`market_snapshot`, `fundamentals`, `live_quote`, `price_history`,
`financial_statements`) routes through it. A tool cannot bypass the gate; a test
enumerates the tool surface and fails if a resolving tool touches a non-gated
capability. There is **no** US (or any) default: an unqualified multi-listed
ticker is `AMBIGUOUS`; an unknown venue is `NOT_COVERED` (not `AMBIGUOUS`); FX
and crypto are first-class asset classes that never inherit an equity country
universe; a wrong-currency/venue answer is discarded. Instrument identity carries
the exchange and MIC where known.
**Why:** The previous round gated only the quote fallback path, so
`market_get_quote` was safe while `fundamentals_get_company_profile` silently
returned the US ADR of a multi-listed issuer and `market_snapshot` defaulted
unqualified lookups to the US — the original defect, reachable by omitting a
parameter.
**Impact:** Extends ADR-020/021/022. `market_unknown` now maps to
`not_covered`. New `financial_statements` capability serves the persisted
`FundamentalsCache` (parse-once, deterministic). Source health records from the
live path, keyed by source × market × asset class. Macro generic measures are
`AMBIGUOUS` even with a geography, and macro rows are newest-first with units.

---

## ADR-024 — Generic macro aliases never narrow silently; recognition ≠ coverage (2026)
**Decision:** A generic macro alias (`CPI`, `INFLATION`, `POLICY_RATE`, …) resolves
only when it names exactly ONE measure; a multi-meaning alias is AMBIGUOUS with
named candidates, and a recognised concept with no registered series (`PMI`) is
NOT_COVERED. An index series carries its `unitBase` (e.g. `1982-84=100`) so the
number is meaningful. Macro rows are newest-first with an explicit `asOf`. A
venue the system recognises but does not cover (`CME` → `DERIV`) is NOT_COVERED,
not "unknown venue" — recognition and coverage are distinct. FX/crypto payloads
state `served: live` and echo the requested symbol, since the vault holds
equities only. Warnings are de-duplicated, and a slow source cadence marks data
"delayed" (a transformation, not a quality warning).
**Why:** CPI silently resolved to the index level, `ES/CME` read as "unknown
venue", and the FX payload said "not in the universe" beside a valid quote — each
a confidently-wrong or self-contradictory answer.
**Impact:** Extends ADR-020…023. `macro_resolve` in TS is the single alias table
(the Python tool asks it before falling back locally). `get_source_health`
enumerates the declared source registry so a source with no runs is `unknown`,
not absent.

## ADR-025 — Skills are versioned procedures on the existing runtime; generated skills are inert (2026)
**Decision:** A Phase-3 skill is a versioned procedure (`skill.json` + `SKILL.md`)
executed through the **existing** Phase-1 `execute_run` graph — no new runtime or
tool registry. The skill registry, default-deny permissions and lifecycle live in
Python (`python/harness/skills/`) and persist in `eclipse-memory.db` (the Phase-3
`SkillStore` is now an alias for `EclipseMemoryStore`; see ADR-026). Instructions
are data, not a security boundary; permissions and the tool allowlist are
enforced in code on the composed `AgentConfig`. The learning engine only creates
inert candidates; promotion to an active skill is explicit, evaluated and
operator-gated.
**Why:** Duplicate infrastructure and autonomous self-modification are forbidden,
and prose cannot be a security boundary.
**Impact:** Phase-3 tables in `eclipse-memory.db` (idempotent migrations; legacy
rows imported once from `agent-memory.db`). Runtime skills live under
`python/harness/skills/library/`, distinct
from the coding-agent `skills/` folder. Front door adds `/api/skills/**`,
`/api/learning/**`, `/api/skill-executions/**`, `/api/skill-drafts/**`,
`/api/evaluations/**` and a Skills tab. pydantic reused (no Zod). See
`docs/harness/phase-3-architecture.md`.

## ADR-026 — Eclipse-Memory is a separate SQLite database and service (2026)
**Decision:** A dedicated SQLite database `eclipse-memory.db` and service
(`python/harness/eclipse_memory/`) become the control layer for agent memory,
user preferences, episodic/semantic/procedural memory, corrections, mistakes,
skills, skill versions, learning candidates, evaluations and promotion history.
Skill definitions remain reviewable files; runtime state lives in the DB
(Option C). The Phase-3 `SkillStore` aliases `EclipseMemoryStore` (one registry);
existing skill rows are imported once, idempotently and non-destructively.
`agent-memory.db` remains the run/replay store (`HarnessRun`, `HarnessEvent`,
`HarnessToolExecution`, `RetrievalRecord`, `ResearchReceipt`, the learning
recurrence ledger) — the two stores are deliberately split so a large run history
never bloats the bounded control database.
**Why:** Audit root cause — memory was never written and never recalled, and the
system prompt promised tools that did not exist.
**Impact:** New DB + `memory_tools.py` (`memory`, `skill_list`, `skill_view`),
`/api/eclipse-memory/**`, and an Eclipse Memory tab. `execute_run` recalls scoped
memory into every run. Prompt corrected to real capabilities. Path via
`ECLIPSE_MEMORY_DB_PATH`. See `docs/harness/phase-3-memory-progress.md`.

---

## ADR-027 — Evidence-grounded answering: a deterministic research flow over the existing retrieval layer (2026)
**Decision:** Add one shared Python package `python/harness/research/` that turns
an objective into a typed research mandate, retrieves each fact leg through the
*existing* Financial Retrieval Layer, produces deterministic per-leg coverage,
validates structured claims against actual evidence, computes named metrics in
pure Python, and persists a bounded research receipt. It adds no agent loop, no
model adapter, no second retrieval system and no second database. The model
interprets and explains; the harness owns coverage, calculation truth, structural
validation and the accept/partial/reject decision. Point-in-time `asOf` is
explicit and enters cache identity; `NormalizedFinancialObject` gains additive
`basis`/`publishedAt`. Receipts live in `agent-memory.db` (idempotent DDL), never
in `eclipse-memory.db` or JDdS.
**Why:** Phase 2 retrieval produced provenance and conflicts but nothing turned
an objective into required facts or gated the model's citations against evidence.
A shared flow is reusable by every financial agent (and future workflow nodes)
rather than each rebuilding citation logic.
**Impact:** New `/research/*` runtime endpoints and `ResearchReceipt` table; 61
new tests; general/unsupported chat is unchanged (`supported=false`). Full
decision set: ADR-H15…H19 in `docs/harness/decisions.md`; progress in
`docs/harness/phase-4-progress.md`.

---

## ADR-028 — Phase 4 hardening: deterministic identifiers, gated live chat, honest semantic evaluation (2026)
**Decision:** Evidence/calculation identifiers use SHA-256 content digests (not
the salted built-in `hash()`); a supported `financial_comparison` is routed into
the evidence gate before the agent graph and never silently downgraded; period
matching is canonical (no substring-of-digits); a versioned human-labeled
semantic-support evaluation reports false accepts/rejects per slice, and
production claim status stays `needs_review` where support is unproven.
Supersession links come only from explicit source revision metadata.
**Why:** The first Phase 4 cut had non-reproducible receipt hashes, a coverage
gate that let missing required metadata pass, no live wiring, and no way to
measure semantic support without over-claiming.
**Impact:** `python/harness/research/{periods,ids,synthesis,supersession,run}.py`
+ `eval/`; additive `research` on `HarnessRun`/`RunResult`; TS `ResearchRunInfo`
contracts + `/api/harness/runs/[id]/receipt` + `ResearchEvidencePanel`. Full
decisions: ADR-H20…H22 in `docs/harness/decisions.md`.

---

## ADR-029 — Bounded web escalation keeps answers evidence-grounded when structured data cannot (2026)
**Decision:** When structured retrieval is empty, stale, missing a requested
fiscal period, or lacks required metadata, the research flow escalates a leg
through a fixed hierarchy — structured → primary-source web (SEC/IR/regulators)
→ bounded reputable secondary web — using the existing web bridge and a single
`ResearchBudget`. Every numeric web fact must pass a deterministic validator
(fetched-page id, verbatim `sourceSpan`, value-in-span, no contradicting period,
metric/period/currency/basis match) before becoming evidence. Coverage gains
distinct statuses (`no_matching_period`, `stale`, `qualified`), and a missing
consolidation basis qualifies the value with disclosure rather than failing it.
**Why:** Stopping at an unrelated structured row produced unhelpful answers; but
"answer anyhow" must never mean invent. A snippet is not a number, a page
instruction is not a fact, and the model cannot decide a source is trustworthy.
**Impact:** `python/harness/research/{budget,web_facts,escalation}.py`;
`retrieval/web.py` serves `financial_statements`; receipt carries escalation +
budget; evidence panel shows tier/dates/period/span. Full decisions: ADR-H23/H24
in `docs/harness/decisions.md`.

---

## Decisions implied by the code (not yet formal ADRs)

These are real, load-bearing, and currently only documented in prose. Promote one
to an ADR if it gets challenged.

- **SQLite-only JDDS.** PostgreSQL was removed along with the old daemon.
  Reintroducing `DATABASE_URL`/pg tooling would be a new ADR.
- **Keep-alive tabs, single page.** Tabs mount on first visit and stay mounted;
  no URL routing for main screens.
- **In-process schedulers.** Cron runs inside the Next.js server (not Vercel-
  friendly by design; a `POST /api/cron/run` endpoint exists for hosted setups).
- **Synchronous-write discipline.** Bulk writers yield and sleep by design
  because better-sqlite3 blocks the event loop.
- **Separate market-workspace engine.** The Chart Workspace tab (tab id
  `market-workspace`) has its own panel engine rather than reusing the widget
  workspace.

---

## ADR-030 — Resilient multi-source research: structured failure diagnostics, independent routes, bounded retry (2026)
**Decision:** Web search/page fetch return a structured RetrievalDiagnostic (provider, category, HTTP status, latency, timeout, result count, bytes, parse outcome, retryability) rather than an opaque UNAVAILABLE; a JSON source document is accepted instead of rejected as 'not HTML'. Structured retrieval is one route among several: a direct SEC EDGAR source (tier primary, US issuers, identity-gated) and an operator-configurable second search provider (vault keys SEARCH_API_CONFIG/SEARCH_API_KEY) join the keyless DuckDuckGo default, with the source policy as data in 
etrieval/planner.py (inancial_statements → [SEC, JDDS, WEB]). The loop retries only transient failures with bounded backoff, switches to the next independent provider, targets unresolved legs, and records a stopReason. Skill learning stays operator-gated and automatic promotion remains blocked.
**Why:** The NVDA run could not tell 'the web had nothing' from 'every route is broken'. Verified causes: DuckDuckGo's HTTP 202 anti-bot page parsed to zero results and returned []; a valid pplication/json SEC XBRL response was rejected by a content-type gate; escalation discarded the failure reason; and all web routes shared one transport.
**Impact:** src/lib/{retrieval-diagnostics,web-search,web-research}.ts, data-bridge.ts, python/harness/retrieval/*, python/harness/research/*, the NVDA labeled eval, and an operator smoke test. Full decisions: ADR-H25–H28 in docs/harness/decisions.md.

---

## ADR-031 — Global market research: truthful capability matrix, suffix-aware identity, declared UA, provider eligibility (2026)
**Decision:** Coverage is a per-market CAPABILITY MATRIX (recognition / searchable universe / quote / history / fundamentals / official filings / web+documents / observed health / live-checked) rather than a country list, so a listed country is never read as 'every capability works'. Source health is keyed by route dimensions (source x market x assetClass). Instrument identity is global and suffix-aware: a recognised exchange suffix is split into an implied market and the vault is queried for both the bare code and the suffixed form; an unknown suffix is never guessed. Providers are gated by eligibility (SEC is skipped for non-US issuers, not attempted-then-failed). The shared fetch transport sends a declared email-contact User-Agent (SEC requires it; verified), and handles JSON/XML/XBRL plus bounded text-PDF extraction (scanned PDFs reported, not garbled). Learning candidates carry run diagnostics and explicit regional scope, remain inert, and promotion stays operator-gated.
**Why:** Real non-US runs (TSMC/Samsung/Petrobras) failed US-centrically. Verified causes: browser-UA spoof gets 403 from SEC/TSMC IR while a declared email UA gets 200; the vault stores bare local codes while users type suffixes (2330.TW returned not_found though 2330 on TW existed); the retrieval planner ignored SEC's US-only supports() gate; source-health collapsed runs to (market, assetClass) producing duplicates; get_coverage told the agent to stop when JDdS lacked a ticker.
**Impact:** src/lib/{markets,web-research,web-search,retrieval-diagnostics}.ts, src/lib/harness/*, src/lib/fundamentals/providers/sec-edgar.ts; python/harness/{finance_tools,retrieval_tools,prompts}.py, python/harness/retrieval/structured.py, 
esearch/escalation.py, skills/learning.py, eclipse_memory/{schema,store}.py. Full decisions: ADR-H29..H32 in docs/harness/decisions.md.

---

## ADR-032 — Reliability & global-research hardening: capability-specific health, distinct route categories, a deterministic comparability gate (2026)
**Decision:** (1) The truthful-capability tools (`get_capability_matrix`,
`get_research_health`) are read-only and in the Eclipse agent allowlist. (2) A
tool's own `timeout_ms` is authoritative; the agent `toolTimeoutMs` is only a
ceiling, and optional news enrichment has its own bounded budget. (3) Source
health is keyed `(source × market × assetClass × capability × probeKind)`: a
healthy quote never makes statements/filings healthy, zero attempts stays
`unknown`, and fixture probes are labelled and excluded from live health. (4) The
route planner reports distinct categories (ineligible / not_implemented /
unconfigured / provider_failure / no_instrument / no_data / no_matching_period /
stale_data / invalid_document) so a skip is never an outage. (5) Documents
distinguish `too_large` / `empty_response` / `javascript_only` /
`unsupported_document` / `parse_failure`, preserve title/document-id/publication
metadata, stream to a bounded size, and refuse a value-less XBRL taxonomy. (6) A
comparison is permitted only when the legs are the same fact for the same entity
— `research/comparability.py` blocks a demerger/ticker reuse, unequal durations
(9M vs 12M), consolidation basis, metric definition, currency, unit, scale or an
unstated restatement, with the exact reason; each verified leg is still reported
and no misleading percentage is computed. The model is never the validator.
**Why:** The international runs recorded `TOOL_FORBIDDEN` for
`get_capability_matrix`, a 20s news timeout despite a declared 30s budget,
`unknown — 0 ok / 0 fail` health rows beside a `configured` coverage claim, SEC
attempted for non-US issuers, and correctness risks (Tata demerger, 9M vs 12M,
standalone vs consolidated, gross vs operations, issuer currency vs thousands,
EPS after a subdivision) that only the model understood.
**Impact:** `python/harness/{agents,finance_tools,retrieval_tools,tools,graph}.py`,
`python/harness/retrieval/{routing,layer}.py`,
`python/harness/research/{comparability,engine,run,receipt,citations}.py`,
`src/lib/harness/{capability,coverage,data-bridge,types}.ts`,
`src/lib/{web-research,retrieval-diagnostics}.ts`, `scripts/test-python.js`.
Progress: `docs/harness/phase-4-progress.md` (Phase 8).

---

## ADR-033 — Aurora sentiment becomes an explainable Market Regime (2026)
**Decision:** The Aurora glow is driven by a transparent **Market Regime** model
(`src/lib/regime/`) rather than the opaquefixed 60% price / 40% coarse RSS blend.
A reading is a set of named components (price & breadth, volatility/options,
macro/risk, news/narrative, positioning), each exposing its score, the weight
actually used, availability, timestamp, source and confidence. Weights are
renormalized over the available set; missing inputs lower confidence instead of
defaulting to neutral, stale inputs are excluded, and a missing core
price/breadth input makes the whole reading UNAVAILABLE. The taxonomy is
Risk-on broadening / Fragile rally / Mixed / Risk-off / Narrative shock /
Unavailable. Scope is explicit (active selected market | US | global), and all
inputs come from JDDS only via one new contract `GET /api/regime`. The glow
stays decorative (`pointer-events-none`); a new accessible top-bar control opens
the interactive frosted-glass breakdown.
**Why:** The old model was hardwired to US indices, exposed no confidence / data
age / provenance, mixed fixed weights, and could be influenced by cached or
fallback data — attractive but not trustworthy. The new model must never present
simulated/fallback/stale data as live sentiment.
**Impact:** `src/lib/regime/*`, `src/app/api/regime/route.ts`,
`src/components/layout/aurora-glow.tsx`,
`src/components/layout/market-regime-control.tsx`,
`src/components/layout/top-bar.tsx`, `src/components/ui/Aurora.tsx` (added `dim`),
`src/components/screens/stock-chat.tsx` (`be:ask-eclipse`). `aurora-sentiment.ts`
retains its palette/visual helpers. See `docs/ARCHITECTURE.md` › Market Regime.

## ADR-034 — Memory/skill reliability: enforced contracts, measured retrieval, isolated scopes (2026)
**Decision:** Tighten the existing Eclipse-Memory and runtime-skills system without
rebuilding it. Skill input/output contracts are validated as full JSON Schema
(nested types, arrays, enums, bounds) and manifest `maxToolCalls` is enforced in
the graph; a run may complete while `outputValidated` is false, never conflated. A
version's identity folds in instruction content and reports undocumented drift.
Memory retrieval gets a versioned labeled evaluation set with recorded
baseline metrics, a deterministic lexical-relevance gate for topical memories
(standing preferences excluded), and authoritative cross-user isolation on read
and on suggestion accept/dismiss. The database ownership split is documented:
`eclipse-memory.db` = control (memory + skill lifecycle), `agent-memory.db` =
run/replay store.
**Why:** Output validation only checked top-level `required`; `maxToolCalls` was
metadata-only; editing prose changed behavior without a new identity; off-domain
queries recalled unrelated memories; and user-scoped retrieval could leak another
user's rows. None of this required a second registry, agent loop or database.
**Impact:** `python/harness/skills/schema_validation.py`, `skills/{manifest,
registry,runtime,evaluation}.py`, `eclipse_memory/{retrieval,service,store}.py`,
`python/harness/{graph,schemas}.py`, `eclipse_memory/eval/`, `src/lib/harness/
errors.ts`. ADR-H45…H47 in `docs/harness/decisions.md`.


## ADR-035 — Autonomous-but-governed learning: provider layer, structured skill patches, hybrid namespaces, prompt segments (2026)
**Decision:** Add four capabilities without relaxing a safety invariant. External
memory is a dedicated `MemoryProvider` layer over the existing MCP boundary —
external results are `provenance=external_provider`/`verified=false`, fenced,
native-first routed, never promoted; external writes require an explicit user
request AND operator approval, and automatic external writes are absent by
construction. Self-improving skills are structured JSON-pointer patches over an
allowed-field set that always create a NEW immutable `SkillVersion`; a stale base
version is rejected, activation requires a passing evaluation, canary is limited
to safe non-mutating skills, and rollback (manual or automatic on a regression)
is atomic and preserves both versions. Memory retrieval uses logical namespaces
plus a bounded hybrid score whose semantic term can only nudge an already-
authorized memory. The prompt is split into immutable segments with an
identity-only `prompt_cache_key`, and skills are injected as a bounded relevant-
only manifest.
**Why:** The product must be autonomous in discovering, proposing, testing,
versioning, activating, monitoring and rolling back improvements — but never
autonomous in silently changing truth, permissions, financial-retrieval rules or
irreversible behavior. Each capability therefore ends at a reviewable, versioned,
reversible or clearly-labelled boundary.
**Impact:** new `python/harness/memory_providers/`, `python/harness/prompt_segments.py`,
`python/harness/skills/{patches,versioning}.py`, `python/harness/eclipse_memory/hybrid.py`;
`memory_tools.py`, `service.py`, `graph.py`, `main.py`, `agents.py`,
`eclipse_memory/{policy,schema,store}.py`, `skills/{manifest,registry,evaluation}.py`;
migration 13; routes `/memory-providers/*` and `/skills/{id}/version-history|patch/**`;
TS skill/memory clients + a patch-version UI panel. ADR-H52—H55 in
`docs/harness/decisions.md`.

## ADR-036 — Long-lived sessions, named profiles and reversible file editing (2026)
**Decision:** Add a durable `ChatSession` (metadata + a bounded deterministic
summary) with a run-belongs-to-session / session-belongs-to-profile link and a
ranked, filtered, bounded session search — history is context, never current
evidence, and a summary is never auto-injected. Add named profiles as a metadata
registry over `.black-eclipse/profiles/` with READ-ONLY inheritance and
request-scoped isolation. Make the Markdown projection editable only through a
targeted, atomic, versioned API (expectedVersion guard, temp+fsync+rename,
structured revision history + rollback + diff); SQLite stays canonical.
**Why:** Users need long-lived sessions and named profiles for real isolation,
and hand-editing a projection must not be able to lose a concurrent edit, leave a
partial file, or lack an audit trail — without replacing SQLite or adding
infrastructure.
**Impact:** `persistence.py` (ChatSession + scope columns), `session_index.py`
(summary), `eclipse_memory/profiles.py`, `schemas.py` (`RunRequest` ids),
`main.py` (`/sessions*`, `/profiles*`, `/summary`, search filters), `graph.py`
(session/profile wiring), `src/lib/harness/{memory-files,run-service,
eclipse-memory-{client,browser,types},python-client}.ts`, new `/api/sessions/**`,
`/api/profiles/**`, `/api/eclipse-memory/files/{edit,history}`, and the Memory
Control Room tabs. ADR-H56—H58 in `docs/harness/decisions.md`.

## ADR-037 - Floating overlays must be portaled; app-wide z-index tiers (2026)
**Decision:** Every floating surface (drawer, dialog, modal, fullscreen panel,
chat dock, toast) renders through `createPortal(document.body)` - never inline -
and uses a single documented z-index scale: fullscreen panels `z-[80..86]` <
floating chat dock `z-[90]` < drawers/dialogs `z-[100]` < toasts `z-[110]`. The
Memory Control Room's six hand-rolled overlays are replaced by one shared
primitive (`src/components/screens/eclipse-memory/memory-overlay.tsx`:
`MemoryDrawer` + `MemoryModal`) that owns the portal, Escape-to-close and body
scroll lock, a sticky header, and the width tiers.
**Why:** The Memory screen is rendered inside the app shell's `glass-card`
container, which uses `backdrop-filter`/`transform` and is therefore a
containing block + backdrop root. An inline `position: fixed` drawer is scoped to
that container: it clipped, sat under the header, and overlapped the floating
chat dock. The overlays also used `z-50`, i.e. below the dock (`z-[90]`), so
they rendered behind it. Hand-rolling six near-identical overlays had let their
widths, backdrops and structure drift apart - the visible "overlapping / not
properly structured" symptom.
**Impact:** `memory-overlay.tsx` is the one place the Memory overlays are built;
`skills-screen.tsx` toast moved to the `z-[110]` tier. The rule applies to any
future floating surface. The frosted-glass hard rules (see the
`black-eclipse-ui` skill) still require the tint to stay <= ~0.55 alpha and the
portal to escape transformed/animated ancestors.

## ADR-H65 - Memory recall surfaced as a content-free activity line

Canonical text: docs/harness/decisions.md ADR-H65. memory.retrieved maps to
one activity item (kind: 'recall', Brain icon) in src/lib/agent/events.ts, with
counts and character budget only; selected <= 0 or an absent/malformed selected
emits nothing; memory ids, excluded records and memory text never reach the UI.
No run-result field is added - the existing activity passthrough is the single
mechanism for this class of fact, and the line stays content-free (the same
privacy posture as the dropped-context seam).

## ADR-H66 - Unknown context windows are operator-declarable; ModelSettings accepts camelCase

Canonical text: docs/harness/decisions.md ADR-H66. ModelSettings gains an
optional bounded context_window (camelCase contextWindow); the budget resolver
prefers override then declared then catalog; blank stays unknown. ModelSettings
also generates camelCase aliases (to_camel + populate_by_name) - fixing a
pre-existing bug where the TS front door's baseUrl/apiKey were silently dropped
by pydantic. Settings > AI / LLM offers a numeric window field only when the
catalog cannot resolve one; an emptied field clears the declaration.


## ADR-038 - MCP config round-trip integrity: a save can never silently widen authority (2026)
**Decision:** `upsert_mcp_config` merges from the incoming model's `model_fields_set`, not `if value is not None`: absent means preserve, explicitly present means replace (including explicit `null`/`false`/`{}`/`[]` for clearing). An omitted field cannot be reset by a partial save; the UI can still clear a field because it always sends every field it owns. This makes a save provably unable to widen authority by omission (`trust`, `enabled_effects`, `tool_effects`, `data_source_tools`, `confirmed_catalog_digest`, `selected_tools`). `env` keeps its write-only merge; `install_mcp_integration` is create-if-absent; `public_dict()` emits the raw operator-set bounds so the wire is lossless. A pure TS module (`src/lib/harness/mcp-draft.ts`) owns view<->draft<->input mapping.
**Reason:** The Phase-6 field set lived only on the wire, not in the UI payload. Re-saving a server through Settings silently downgraded `untrusted`->`full`, disabled resources/prompts, dropped the data-source declaration and every tool effect, and invalidated the catalog confirmation - a silent authority widening.
**Impact:** python/harness/mcp/{config,runtime,introspection,oauth_flow,manager}.py, python/harness/service.py, src/lib/harness/{mcp-types,mcp-draft,mcp-client}.ts, src/components/screens/mcp-settings.tsx + src/components/screens/mcp/*, src/app/api/harness/mcp/{integrations/[id]/install,supply-chain}/route.ts; tests test_mcp_config_roundtrip.py, test_mcp_example_config.py, mcp-draft.test.ts. See docs/harness/decisions.md ADR-H74 and docs/harness/mcp-ui-parity-progress.md.

## ADR-039 - The release gate is local and runnable (2026)
**Decision:** Delete the unreachable `Black-Eclipse-site/.github/workflows/` (GitHub reads only root `/.github/workflows`; the repo git root is above the app dir) and replace it with ONE local gate: `npm run check:all` runs prisma generate, typecheck, lint, `npm test` and `npm run test:evals` in order, failing on the first error. The three eval gates (retrieval, contradiction, compaction) move into `npm test` via `scripts/test-evals.js` (offline, ~0.7s) using the explicit-`sys.path` launcher; the dead `semantic_cli` reference is removed. The CHANGELOG obligation is enforced by `.githooks/commit-msg` (non-doc change must stage the CHANGELOG; `SKIP_CHANGELOG_CHECK=1` bypass).
**Reason:** The release gate was fictional three ways: a CI job that could not pass, a workflow GitHub never read, and eval floors no local command ran.
**Impact:** .github/ removed; scripts/test-evals.js + scripts/check-all.js (new); package.json (`test:evals`, `check:all`, `test` includes evals); .githooks/commit-msg (new); scripts/install-git-hooks.js. See docs/harness/decisions.md ADR-H75 and docs/harness/engineering-hardening-progress.md.

## ADR-040 - A theme preset is holistic: it carries a partial ChatBot-backdrop snapshot (2026)
**Decision:** A preset is more than design tokens. `ThemePreset` and
`UserThemePreset` carry an optional **partial** `background` snapshot
(`Partial<BackgroundPrefs>`, validated by `normalizePresetBackground`). Selecting
a preset previews its backdrop (`useBackgroundStore.preview`, non-persisted) and
Apply commits it (`applyPreset(theme, background)`); the snapshot is **merged over
the user's live background prefs**, so a preset that only sets the wordmark keeps
the user's wallpaper and vice versa. `ChatWordmark` reads `previewPrefs ?? prefs`
so glyphs update live. The theme store calls the background store's adapter
(`applyBackgroundToDocument`) rather than subscribing to it — a store-to-store
subscription was a module **cycle** (`backgrounds.ts` imported `useThemeStore`);
`refreshBackground()` re-asserts the saved backdrop after every theme write.
**Reason:** Applying a preset changed colors/fonts/sidebar but left the ChatBot
landing (the most visible surface) untouched, because the two stores had no
coupling. The separation was intentional for *manual* backgrounds but wrong for a
unified "look".
**Impact:** src/lib/theme/{tokens,store,index}.ts, src/lib/backgrounds.ts,
src/components/screens/customization-settings.tsx (+ extracted
`customization-preview.tsx` to stay under the size ratchet),
src/components/chat/chat-wordmark.tsx, src/components/layout/{sidebar,top-bar}.tsx,
src/app/globals.css (`--font-heading`). Tests: tokens/store/backgrounds + new
preset-snapshot cases. See docs/ARCHITECTURE.md.

## ADR-041 - Icon set is Phosphor behind a single aliased surface (2026)
**Decision:** The UI renders **Phosphor** (`@phosphor-icons/react` ^2.1.10) instead of lucide-react. Every icon is imported from ONE module, `src/lib/icons/index.ts`, which re-exports each Phosphor glyph under its original Lucide name (e.g. lucide `Search` → Phosphor `MagnifyingGlass`) plus `LucideIcon` (Phosphor `Icon`), so call sites and the `LucideIcon` map types stay unchanged and the set can be swapped in one file. Components never import an icon library directly. Selected/active states use Phosphor's `weight="fill"` prop — Phosphor outline glyphs are filled paths, so `fill="none"` would erase them; accent-colored fills use a className text color instead.
**Reason:** Lucide is ubiquitous and reads generic; Phosphor's weights (including duotone) and shape language are distinctive and suit the dark glass UI. Aliasing avoids a 165-file / 216-icon rename while confining the dependency to one module.
**Impact:** `src/lib/icons/index.ts` (new). Every icon-importing module imports from `@/lib/icons`. Three files that render icons gained a `'use client'` boundary (`components/chat/{chat-history,markdown}.tsx`, `components/screens/portfolio/fund-store.ts`) because Phosphor icons read `useContext`. `lucide-react` removed; `@phosphor-icons/react` added. `components.json` (shadcn CLI `iconLibrary`) still says `lucide` for generated components — reconcile when the CLI is next run. See `docs/NAVIGATION.md` (By task).

## ADR-042 - The Agent Workspace is a global observability panel fed by the ONE existing event stream (2026)
**Decision:** Add an execution-observability layer, the **Agent Workspace**, that shows what the agent is doing in real time (activity, tasks/plan, changes, context, terminal, research, browser, computer-use, artifacts, approvals, telemetry) without flooding chat. It is mounted **globally and portaled** from `src/app/layout.tsx` (plus a top-bar toggle), so it coexists with the existing LEFT navigation rail and every keep-alive screen; it modifies none of them. It is fed by the **single existing** chat SSE stream: `src/lib/agent/registry.ts` calls one new seam, `ingestHarnessFrame(event, data)`, from the frame parser it already runs � no second event bus, agent loop, or model adapter. The workspace owns its own normalizer (`src/lib/agent-workspace/normalize.ts`) because it maps a superset of the runtime's ~140 event types into a different shape (categories, changes, artifacts, telemetry), while reusing the chat's human labels (`toolLabel`). Live state is folded by a pure reducer into an immer draft, committed at most once per 150 ms; duplicate envelopes are dropped by id, out-of-order frames are applied and counted, and lists are bounded. Large output is an `ArtifactRef` handle opened in a Viewer, never inlined. Approvals reuse the existing decide endpoint (the UI is a surface, not the authority).
**Reason:** Tool-heavy runs produced large outputs and per-tool detail with no single surface for "what is Eclipse doing", and a naive second event bus / second agent loop would duplicate the runtime's sole event owner. The app also had no generic right-side observability panel, and the shell (`stock-chat.tsx`) is already at its size ratchet � a portaled global mount avoids touching it at all.
**Impact:** New `docs/agent-workspace.md`; `src/lib/agent-workspace/**` (types/normalize/reducer/store/stream/history/ingest/format + tests); `src/components/agent-workspace/**` (dock + panels + Viewer + reachability test); one import line in `src/app/layout.tsx`; one call in `src/lib/agent/registry.ts`; the top-bar toggle. Persistence keys `black-eclipse:workspace-*` (never the `be_sidebar_*` keys). Honest gaps (no live screenshot pixels, subsystem events without a run id do not reach a run stream, cost only when reported) are stated in the doc.

**Amendment (2026-10-07) — the workspace is now a docked right SIDEBAR, not a floating panel.** The portaled, floating, 13-tab overlay read as "not even a sidebar" and buried the useful output under telemetry noise. Superseding the *placement* and *panel set* above: the workspace is now a real full-height glass COLUMN mounted in the app shell's primary row (`src/components/screens/stock-chat.tsx`, sibling of the main panel, so the main panel shrinks rather than being overlapped — the same pattern as `TerminalDock slot="right"`), resizable on its inner edge (width persisted, clamp 300–760 px, no hard border frame). Its tabs are minimized to **Output** (default), **Changes**, **Approvals**, **History**; the overview/activity/tasks/context/telemetry/research/browser/computer/artifacts panels were removed as noise. The new `OutputPanel` is a ChatGPT / Claude Code / Kimi-style feed: each tool call / command / file write expands in place to render its bounded large output (via the shared `ArtifactContent`), so big results never flood chat. The one-stream ingest seam, normalizer, reducer, bounded state and honesty rules are unchanged; pin/auto-focus and their persistence keys were removed. Shell size-ratchet bumped 1270 → 1272 for the import + mount lines.

## ADR-043 - Structured responses ride the existing Markdown stream as a fenced block; the renderer is a registered component registry (2026)
**Decision:** Add the **Interactive Response Engine**: an assistant turn may include ONE fenced ```eclipse-response block whose JSON body a versioned zod contract (`src/lib/response/contract.ts`) validates, and which renders through a registry of components (`src/components/response/response-view.tsx`) — metric grids, sortable/filterable tables, ECharts charts, SVG diagrams, timelines, citations — inline in the existing chat. It reuses the **existing** Markdown renderer (`components/chat/markdown.tsx` intercepts the fence language), the **existing** ECharts dependency (lazily imported), and the **existing** message persistence (the fence is stored in `Message.content`; reopening re-parses it). No second chat engine, stream, transport, or artifact store is introduced.
**Reason:** The documented gap (`docs/chat-ui-audit.md` §16, Risk R7) was that the runtime's terminal output is plain Markdown with no structured wire contract, so structured blocks/charts were deliberately not built. A fenced block is the smallest real producer→renderer contract that needs no Python protocol rewrite, works in both chat surfaces unchanged, persists for free, and degrades safely (unknown/malformed blocks become diagnostics, never code execution, never a lost answer).
**Impact:** New `src/lib/response/**` (contract/parse/chart-option/diagram-layout + tests) and `src/components/response/**`; `components/chat/markdown.tsx` gains a `streaming` prop and the fence branch; `chat-history.tsx` passes it. `zod` promoted to a direct dependency (was transitive). `prompts.py` gains a "Structured answers" section so agents can author the block when it helps. No Python protocol, database schema, or persisted-conversation migration. Security posture: structured JSON only — never model-authored JS/HTML; per-block resource limits; per-block error boundaries.

**Amendment (2026-10-10) — full build-out.** The previously deferred capabilities are now shipped by reusing existing infrastructure: a deterministic **response planner** (`src/lib/response/planner.ts`; GFM tables → interactive tables, link-only source lists → citations, for every settled answer, no model call); **backend-driven controls** (`controls-block.tsx`) re-entering the existing agent loop via `onFollowup`; **export** JSON/CSV/PNG/PDF (`export.ts`; PNG via an ECharts instance registry, PDF via lazy `jspdf`+`jspdf-autotable`); **Artifact Center save** via the existing `registerArtifact`; a **`financial_chart`** block wrapping the existing `ChartWidget`; a **`mermaid`** block (lazy, `securityLevel: 'strict'`). Still out of scope (documented, not faked): React-Flow *editable* graphs, server-side table pagination beyond the 2000-row cap, and PDF embedding of unmounted/financial charts. See `docs/interactive-response-engine.md`.

**Amendment (2026-10-11) — rich block family + link hardening.** The catalogue grows to the full interactive vocabulary: **`stepper`** (numbered process with per-step status), **`infographic`** (icon cards — icons resolved through a semantic allowlist in `src/lib/response/icons.ts`; the model names a key, never a component or import path), **`report`** (a multi-section container whose section `blocks` are validated recursively like `tabs`), **`node_graph`** (a *selectable* graph that reuses the same deterministic `diagram-layout` engine — no second graph library; nodes are focusable/selectable and reveal their `detail`), **`action_group`** (PROPOSED next steps whose click sends a follow-up prompt into the existing agent loop — never a privileged backend call), and **`artifact`** (a reference to the existing Artifact Center, linked via its own download route). Spec-name synonyms are normalized to canonical blocks (`text`→`markdown`, `table`→`data_table`, `source_list`→`citations`, `interactive_form`→`controls`, `execution_timeline`→`timeline`). Every model-supplied citation/artifact link is now **scheme-restricted to http(s)** — bare `z.string().url()` accepts `javascript:`/`data:`, which becomes an XSS vector once rendered as an anchor. The agent guidance in `prompts.py` was rewritten to be more directive and to list the new blocks, **within the unchanged 26410-char ceiling**. All new blocks render through the same registry + `BlockBoundary`, and PDF export represents each. Tests: `src/lib/response/contract-blocks.test.ts`.

**Amendment (2026-10-14) — branching `flow` block + native-flow routing over Mermaid.** A new dependency-free **`flow`** block renders a branching process as frosted HTML/CSS cards: ordered `steps` joined by CSS connectors, each step optionally branching into parallel `paths`. It is distinct from `workflow` (strictly linear icon stages) and from `diagram`/`node_graph` (absolute-positioned SVG graphs) — the native, responsive answer for a flowchart. `mermaid` is now reserved for sequence/ER/class/gantt, and the prompt directs flow/flowchart answers to `diagram`/`flow`/`workflow`, so the heavy `mermaid` bundle stays unloaded for ordinary process answers. New aliases route producer vocabulary (`process`→`workflow`, `process_flow`/`pipeline`→`flow`, `flow_graph`→`diagram`). Rendering reuses the existing registry + `BlockBoundary`; the block is data-only (no model-authored HTML). Tests: `contract-blocks.test.ts`, `render.test.tsx`; `prompts.py` stays within its char ceiling. See `docs/interactive-response-engine.md`.

## ADR-044 - Private per-conversation long-term memory: a first-class `conversation` scope on the ONE Eclipse-Memory pipeline (2026)
**Decision:** A bot chat and each group-room member turn keep their own **private durable memory**, isolated from every other conversation/bot and from ordinary chat. This is implemented as an additive **`conversation` scope** on the existing `MemoryRecord.scope` column, keyed by `scopeId = conversation id` (the run's `sessionId`: `bot-<id>` or `group-<gid>-<botid>`). A `conversation` actor may read ONLY its own bucket, the signed-in user's own `user` rows (when present) and truly-global `general` knowledge — never another conversation. The scope is normalized at the ONE write gate (`EclipseMemoryService.commit_decision` via `decision.resolve_owner_scope`): in a conversation-scoped run with no signed-in user, a personal (`user`) fact is owned by that conversation. Opt-in is explicit: only the bot/group call sites set `memoryScope: 'conversation'`, which the front door maps to `RunRequest.conversationId`; ordinary chat is unchanged. Scheduled bot runs bind the SAME `bot-<id>` conversation so background learning is recalled in chat. `bot_delete` archives the bot's conversation memory (never hard-deletes). No new database, table, or column.
**Reason:** The bots UI documented "no separate memory" — every durable fact landed in shared `general`/unattributable `user` rows, so a bot could neither accumulate its own long-term context nor be isolated from other bots. A separate memory store per bot would violate the one-store/one-pipeline invariants (ADR-026/034); a new scope value reuses the authoritative scope-before-rank filter, the single decision gate and the single persistence path.
**Impact:** `eclipse_memory/{decision,retrieval,service}.py` (`resolve_owner_scope`, conversation candidate gathering + `_scope_authorized`, `forget_conversation`); `memory_tools.py` (default scope + `conversation` enum); `graph.py`/`graph_context.py`/`schemas.py`/`tools.py` (thread `conversationId`/`conversation_id`); `automation/dispatcher.py` (bind `bot-<id>`) and `automation/tools.py` (purge on delete); `routers/memory.py` (scopeId filter + `POST /eclipse-memory/conversations/{id}/forget`); TS `agent/types.ts`, `agent/registry.ts`, `harness/run-service.ts`, `harness/python-client.ts`, `harness/eclipse-memory-browser.ts`, both chat routes, `bot-chat.tsx`, `group-chat-room.tsx`, `bot-detail.tsx`, new `bot-memory-section.tsx`, i18n `en.ts`. Conversation ids remain local labels, not security identities. Tests: `python/tests/test_memory_conversation.py`. See `docs/harness/memory-skills-evolution-plan.md`, `docs/harness/automation-engine.md`.

---

## ADR-045 - Page targeting: a resolvable current-page default, distinguishable summaries, plain-string data sources, one owner policy (2026)
**Decision:** (1) `UiService.get_current_page` resolves the page by explicit `blueprintId`, else `path`, else `title`, else the owner's **most recently updated** page; it always returns `resolution` and, on a choice among candidates, the other `candidates` - it never silently returns row 1. Paths are normalised and `None` never matches; an unmatched lookup is `UI_BLUEPRINT_PATH_UNASSIGNED` when pages exist without a path, else `UI_BLUEPRINT_NOT_FOUND`. A new `GET /ui/current-page` exposes it (the `/ui/blueprints/{id}/current` route is unchanged). (2) `BlueprintSummary` gains `path` and `componentIds` so pages that share a title are distinguishable, and `q` searches path too. (3) `get_blueprint` fetches unscoped and applies the owner rule in the service, so `get_current_page`/`get_layout`/`preview` share ONE policy; a mismatch is the distinct `UI_BLUEPRINT_OWNER_MISMATCH` (HTTP 403), never `unknown blueprint`; read tools pass no owner scope. (4) The UI runtime advertises its valid structured data sources via `get_capabilities()["dataSourceRegistry"]`; the one family is `portfolio:<portfolio_id>:<view>` for the Ledger kinds.
**Reason:** Fifteen blueprint pages can share the title "Main", and there was no active-page notion, no path in the list summary, and path matching could never hit an unset path - so an agent could not unambiguously name a page, and the HTTP route and the agent tool disagreed on owner scope. A `data-table`/`metric-card` had a free-text source with no registry, so no one could know which strings resolve a portfolio. These are contract/data-shape fixes, not new subsystems.
**Impact:** `python/harness/ui/{service,store,model,catalog,tools}.py`, `python/harness/routers/ui.py`, `src/lib/harness/ui-client.ts`; tests in `python/tests/test_ui_{service,tools,api}.py`; docs `docs/ui-engineering.md`, `docs/portfolio-accounting.md`. No new store, table, migration, or agent loop. A page-level icon remains a scoped, unbuilt gap (needs a new model field + renderer; not the chat response-block icon enum).

**Amendment (2026-10-15) - the generic render path + portfolio surfaced end to end.** The page-targeting/data-source work above was contract-only: an agent could name a page and declare a `portfolio:<id>:<view>` source, but nothing rendered it (Pages/Builder render only host widget ids, and `source` config was inert). Two host primitives now close the loop: `data-table` and `metric-card` (`src/lib/workspace/generic-widgets.tsx`, registered in `src/lib/dashboard/registry.tsx` with ids matching the runtime catalog, so the workspace kernel does not drop them). `src/lib/workspace/data-source.ts` is the ONE allow-listed resolver (never an arbitrary URL): it parses the source, fetches through the existing portfolio front door (`src/lib/portfolio/engine-read.ts` -> `/api/portfolio/{id}/query|history|tax-lots`), caches it on a dynamic DataHub topic, and returns rows/columns or a value - or an explicit UNAVAILABLE with the reason. The six bespoke `portfolio-*` catalog kinds introduced earlier were removed: every advertised component is now renderable. Pages cache their arrangement by blueprint revision (`pageStorageKey(id, revision)`) so an agent edit seeds a fresh workspace instead of being shadowed, and Refresh reloads the open page. `ui_verify_page` / `UiService.verify_page` reads a page back and reports per-widget renderability. Remaining gaps (charts, other source families, live push) stay scoped: `docs/ui-engineering.md`.

**Amendment 2 (2026-10-15) - production surface: full renderable vocabulary, more source families, parity, page icons.** The generic render path was broadened so "compose anything" is real, not aspirational. The catalog seed (`builtin_specs`) is now EXACTLY `RENDERABLE_COMPONENTS`, the ids the host registry defines (metric-card, data-table, list, line/area/bar/pie-chart, markdown, status-indicator, empty-state, error-state); the nine never-renderable foundational kinds were removed, and parity is enforced on both sides (python/tests/test_ui_service.py + src/lib/workspace/generic-widgets.test.ts). The resolver gained allow-listed families: market:quote:<SYMBOLS>, market:indices:<MARKET>, market:price:<SYMBOL> (series), news:latest, agent:activity - each backed by an existing read route, cached on DataHub, still never fetching an arbitrary URL. Page-level icons (the previously scoped gap) are implemented: `UiBlueprint.icon`/`BlueprintSummary.icon` with an idempotent add-column migration, agent/HTTP/TS support, and Pages UI rendering. Pages refreshes the open page when its durable revision changes (focus + 20s poll), so an agent edit appears without disrupting a user's local arrangement. Docs: docs/ui-engineering.md.

**Amendment 3 (2026-10-15) - the remaining gaps closed: more source families, push updates, engineer loop proven.**
The resolver gained four more allow-listed families, each backed by an existing read route and tested: tasks:list / tasks:plans, artifacts:list, research:list, and jdds:search:<QUERY> (JDDS instrument search). Live page updates moved from a blind poll to a Server-Sent-Events stream (GET /api/ui/stream): the server watches the runtime's most-recently-updated blueprint (id:revision:updatedAt) and pushes a changed event; Pages reloads the open blueprint only when its durable revision moves (focus + a slow 60s poll remain as fallbacks). The Engineer -> Compose closure is now proven end to end in test_ui_api.py: register an engineered component, discover it via GET /ui/components, add it to a page, and GET /ui/blueprints/{id}/verify reports it renderable. Docs: docs/ui-engineering.md.

**Amendment 4 (2026-10-15) - production hardening: verify every family, no silent widget drops.** erify_page now validates a declared source against ALL families via catalog.validate_source (portfolio, market, news, agent, tasks, artifacts, research, jdds), not only portfolio. And the Pages surface no longer silently drops a blueprint widget whose id the host registry does not render yet: it passes the workspace a knownWidgetIds set = host registry + every id present in the blueprint, and enderDashboardWidget draws an explicit "Needs a renderer" card for it (the Engineer path can add the real renderer). Tests: python/tests/test_ui_service.py, src/app/api/ui/stream/route.test.ts. Docs: docs/ui-engineering.md.

---

## ADR-046 - The Eclipse theme is APP-WIDE: a server source-of-truth plus one canonical origin (2026)
**Decision:** The user's theme stops being a per-browser property. **(1) Server source of truth:** the JDDS `SystemConfig` table (key `eclipse_theme`) owns the single app-wide theme, exposed by `/api/theme` (GET/PUT/DELETE, operator-gated via the existing `guardMutation`). The client store (`src/lib/theme/store.ts`) demotes `localStorage` (`be_theme_v1`) to a per-origin first-paint cache: on boot it hydrates the cache then `hydrateFromServer()` adopts the saved app-wide theme; every edit pushes to the server; Reset issues DELETE. A *successful* null read means "shipped default": if the app-wide theme was never initialized the client MIGRATES its pre-existing per-origin theme up instead of wiping it; after an explicit reset it clears the local override (an unreachable server leaves the cache untouched). **(2) One canonical origin:** when `BE_CANONICAL_HOST` is set, `src/middleware.ts` redirects any other host to it (307, path + query preserved) before the auth gate; `scripts/local-host.js` sets it to the local hostname by default, while `npm run dev:next` leaves it unset so zero-config localhost is unchanged.
**Reason:** `localStorage` is scoped to the browser ORIGIN, so `http://localhost:3000`, `http://127.0.0.1:3000` and `https://blackeclipse` each held their own theme - three visibly different instances of one app. The repo had already solved this exact problem for chat transcripts (server copy + `localStorage` cache); the theme was the last major surface left per-origin. A DB property also makes the theme shared across devices, which is what "app-wide" means.
**Impact:** New `src/lib/theme/server.ts` + `src/app/api/theme/route.ts`; `src/lib/theme/store.ts` (`persistLocal`/`pushThemeToServer`/`clearServerTheme`, `hydrateFromServer`, server-aware `reset` + `useHydrateTheme`); `src/middleware.ts` (canonical redirect) + `scripts/local-host.js` (sets `BE_CANONICAL_HOST`) + `.env.example`. `localStorage` keys are unchanged; user-saved presets (`be_theme_presets_v1`) stay per-origin (a personal library, not the active look). Tests `src/app/api/theme/route.test.ts`, `src/lib/theme/store.test.ts`, `src/middleware.test.ts`. Docs `docs/ARCHITECTURE.md`, `docs/local-hostname.md`, `docs/NAVIGATION.md`. No schema change, no new table, no new agent loop.

## ADR-047 - The Anatomy isometric engine is a declarative response block over a vendored kit; the model authors a SCENE, never code (2026)
**Decision:** A new `anatomy` block type renders an interactive isometric mechanism figure inline in chat. It rides the ONE existing structured-response pipeline (ADR-043): a zod schema in `src/lib/response/blocks/anatomy.ts`, one entry in the renderer registry (`src/components/response/response-view.tsx`), the `finalize`/repair/degrade chokepoint, the Markdown projection, and the `response_block_schema`/`response_validate` read-back (so the model can query the exact field names before emitting). The model authors a **bounded, declarative scene** — parts (a `<kind, x, y, z, w, d, radius, height, corner, tone, lit, label>` slab/cylinder), wires (`from`/`to`/`via`/`tone`), a legend, and optional deterministic **stages** (`{ label, note, readout, lit[] }`) — and the geometry is compiled purely by `src/lib/anatomy/scene.ts` with the MIT-licensed Anatomy-derived kit vendored into `src/lib/anatomy/` (`NOTICE` + `LICENSE` record the MIT origin and the verified upstream commit `e9488296a44211c42701ff71705b7901470ec78f`; blob hashes prove `iso-kit.ts`/`live.tsx` byte-identical). The model never supplies SVG, HTML or code. The renderer is `'use client'` and renders the figure inside a frosted-glass card with a full-page overlay; the **stage is the sole source of live readout text**, animation is discrete (no rAF loop), autoplay is off under `prefers-reduced-motion`, and the interval is cleared on unmount — so the figure cannot invent a value and cannot leak a timer.
**Reason:** The Interactive Response Engine already covers flows, charts, diagrams, timelines, simulators and learning maps — but not a *physical-mechanism* illustration, which is what "explain how a CPU/cache/refinery works" needs. Anatomy (wheresryan22/anatomy, MIT) is exactly that toolkit; its bespoke figures are standalone HTML built by node scripts, which do not fit a chat artifact. Reusing only its geometry primitives and React drawing components, then driving them from a declared scene, keeps the Eclipse posture intact: a registered component registry, no model-authored code path (SEC-001), deterministic model-as-source-of-truth, and a text fallback (the Markdown projection) for surfaces that cannot render it.
**Impact:** New `src/lib/anatomy/` (vendored `iso-kit.ts`, `draw.tsx`, `live.tsx` + `NOTICE`; Eclipse-authored `scene.ts`), `src/lib/response/blocks/anatomy.ts` (schema extracted from `contract.ts`, whose size ratchet it helps satisfy), `src/components/response/anatomy-block.tsx`; `contract.ts` (import + union entry), `normalize.ts` (`anatomy` type aliases + status-tone normalization), `projection.ts` + `export.ts` (projection/PDF cases), `response-view.tsx` (registry). Tests `src/lib/anatomy/scene.test.ts`, `src/components/response/anatomy-render.test.tsx`, the matrix (`contract-matrix.test.tsx`). Docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`. **Not wired:** WebGL/3D and the bespoke lathe/tube parts stay out of runtime (kept in `docs/figures/eclipse-refinery/` as a reference); only slab/cylinder parts render. No new dependency, no new agent loop, no wire-contract change.

## ADR-048 - True 3D mechanism models are a separate `model3d` block compiled to world meshes and rendered in an orbitable WebGL viewport (2026)
**Decision:** `/anatomy` now authors a `model3d` block, not the isometric `anatomy` scene. It keeps ADR-047's trust posture — the model supplies a bounded declarative SCENE (JSON), never meshes, shaders, SVG or code — but the scene is a real 3D graph: `parts[]` carry a `position`/`rotation`/`scale` transform, an optional `parent` (assemblies), material/tone/lit/label, and geometry as either a primitive (`box`, `cylinder`, `cone`, `sphere`, `torus`, `lathe`, `extrude`, `tube`, `gear`) or a **named mechanism recipe** with numeric `params` (`motor`, `gearbox`, `pump`, `valve`, `gauge`, `tank`, `bearing`, `gear`, `pulley`, `belt-drive`, `frame`, `bracket`, `fan`, `heat-exchanger`, `pcb`, `lever`, `spring`). The pure compiler (`src/lib/model3d/compile.ts` + `mesh.ts` + `recipes.ts`) expands recipes, composes parent transforms with a cycle guard, bakes every triangle to world space, grounds the scene, fits the camera and reports anything it cannot place as a diagnostic — it is total and server-safe. The renderer is split: a DOM half (`model3d-block.tsx`) owns the header, numbered key, legend, readout, stage controls and `.glb` download; a `next/dynamic(ssr:false)` WebGL half (`model3d-canvas.tsx`) uses the already-vendored `ogl` dependency for orbit/zoom/pan, lighting, a fading grid and projected hotspots. `glb.ts` is a dependency-free glTF 2.0 binary writer. The legacy `anatomy` block stays registered and renders unchanged for old payloads.
**Reason:** The isometric SVG compiler can only draw what it has primitives for and paints in producer order with no depth buffer; it cannot rotate, compose assemblies or show a machine from another angle, so `/anatomy` collapsed to "a base slab plus cylinders". The two real levers are (1) genuine 3D with depth/lighting and (2) a reusable parametric mechanism kit, so the model composes recognisable assemblies instead of guessing primitives. `ogl` is already a dependency (~15 KB, used by the Aurora background), so no new package and no bundle cost on the initial chat load (the viewport is lazy). Keeping the legacy block avoids a breaking wire-contract change; keeping compilation pure preserves determinism, tests and the no-model-code security posture (SEC-001).
**Impact:** New `src/lib/model3d/` (`names.ts`, `math.ts`, `mesh.ts`, `recipes.ts`, `compile.ts`, `glb.ts`), `src/lib/response/blocks/model3d.ts`, `src/components/response/model3d-block.tsx` + `model3d-canvas.tsx`; `contract.ts`, `normalize.ts` (type aliases), `projection.ts` + `export.ts` (text/PDF cases), `response-view.tsx` (registry), `command-agent.ts` (/anatomy directive), the `system.anatomy-figure` skill. Tests `src/lib/model3d/{mesh,compile}.test.ts`, `src/components/response/model3d-render.test.tsx`, `contract-matrix.test.tsx`. Docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`, `docs/harness/slash-commands.md`, `.opencode/skills/black-eclipse-anatomy/SKILL.md`. No new dependency, no new agent loop, no schema change to existing blocks.

## ADR-049 - Eclipse Canvas is an editable document/code/visual workspace over the ONE Artifact Center; AI edits are typed operations re-applied under a revision guard (2026)
**Decision:** Eclipse Canvas is a persistent, editable workspace for documents, code and visual reports, built **on top of the existing Artifact Center with no second store**. A canvas document IS an ordinary `Artifact` whose bytes are canonical UTF-8 text and whose revisions are the artifact's immutable versions; the canvas kind (`document`/`code`/`visual`) and optional `language` live in the artifact's `metadata` under the key `canvas` (`python/harness/canvas/`, `CANVAS_METADATA_KEY`). `CanvasService` is the ONE canvas writer over `ArtifactService` (create/read/list/save/restore); each save is guarded by the `baseVersion` the editor loaded and serialized by a lock, so a stale save returns `409 CANVAS_CONFLICT` carrying `currentVersion` instead of overwriting. AI assistance is one orchestrator (`CanvasEditOrchestrator`): it builds a strict-JSON prompt, calls the model through the ONE model runtime (`vision.providers.call_model`, task `canvas_edit`), validates the reply with `model_runtime/structured.py`, and **re-validates every operation against the loaded revision**; modes are `ask`/`edit`/`review`/`build`, Ask mode never proposes edits, and a missing model configuration is the honest `CANVAS_MODEL_UNAVAILABLE`. Edits are a **closed vocabulary of typed operations** (`ops.py`: `append`, `replace_text_range`, `replace_section`, `insert_after_section`, `replace_document`, `apply_code_patch`) applied deterministically to current bytes — never a free-form patch, eval, template, or model-authored code. An AI-assisted save sends `operations`, and the server re-applies them to the current revision, so **client content is not trusted**; unknown, ambiguous or stale operations are rejected. Routes are `python/harness/routers/canvas.py` (`/canvas/artifacts*`, operator-gated, owner from `x-harness-user`), proxied by `src/app/api/canvas/[[...path]]/route.ts`, which also resolves the operator's model from the settings vault (`resolveRunModelSettings`) and injects `modelSettings` for `.../edits` (the runtime cannot read the vault). The UI (`src/components/screens/canvas/`) is a three-region workspace: a rail (list/search/create/import), a center editor (Tiptap document with Markdown as canonical content, Monaco code, JSON editor + live `ResponseView` preview for Eclipse response-envelope visuals) with debounced autosave, Ctrl/Cmd+S, version history + restore, export and a `409` conflict UI, and an AI panel with a propose → diff → accept flow.
**Reason:** The Artifact Center stores immutable, versioned, content-addressed files but has no editor, so "make this artifact editable" would otherwise require a second document store with its own versions, owner scope and model path — three new authorities over the same bytes. Reusing the catalog keeps one storage root, one version table and one owner scope. A typed-operation contract (rather than accepting model-authored content or patches) preserves the no-model-code security posture (SEC-001) and makes every AI change reviewable and reproducible; a revision guard is required because keep-alive editors and AI proposals can both hold stale bytes, and silently overwriting would be a data-loss path.
**Impact:** New `python/harness/canvas/` (`model.py`, `ops.py`, `service.py`, `edits.py`), route group `python/harness/routers/canvas.py` registered in `main.py`, tests `python/tests/test_canvas.py` + `test_canvas_api.py`; front door `src/lib/harness/canvas-client.ts` + `src/app/api/canvas/[[...path]]/route.ts`; UI `src/components/screens/canvas/` (`canvas-screen.tsx` + rail/center/workspace/ai-panel/editors); new `canvas` AppTab (`src/lib/app-tabs.ts`, sidebar `config.ts` icon `SquarePen` in the agentic group, `nav.canvas`, deep-link `APP_TABS`, mobile bottom nav, keep-alive block in `stock-chat.tsx`); integrations `/canvas [document|code|report|visual]` (`command-registry` + `native.canvas` returning an open link), Artifact Center "Open in Canvas" for artifacts whose metadata carries `canvas`, and response-actions "Canvas"; new editing dependencies (`@tiptap/*`, lowlight, `monaco-editor`, `@monaco-editor/react`); tests `src/app/api/canvas/route.test.ts` + `src/components/screens/canvas/canvas-screen.test.tsx`. Storage stays SQLite (`agent-memory.db` + artifact files under `.black-eclipse/artifacts`), never Postgres. Docs `docs/canvas.md`, `docs/harness/artifact-center.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`. No new agent loop, no new store, no new database table.

**Amendment (inline, 2026-10-17):** Canvas is **not a standalone surface**. The `canvas` AppTab, the sidebar entry/`nav.canvas`, the deep-link tab, the mobile bottom-nav item and the `/canvas` command were **removed**; there is no external Canvas page. Canvas renders as an **inline pane inside the ChatBot tab** (`stock-chat.tsx`): when `useCommandStore.canvasInlineOpen`/`pendingCanvasArtifactId` is set, the chat column and a right-hand `CanvasPane` (`CanvasScreen inline`) split the view, with a close button; the pane carries the editor and (collapsed by default) the same AI panel. It opens from a response's **Canvas** action (save → inline) and from the Artifact Center's **Edit in Canvas** (`dispatch({tab:'chat', params:{artifactId}})`), never a separate route. The backend, artifact model, typed-operation contract and revision guard are unchanged.
