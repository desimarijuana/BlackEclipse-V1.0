---
title: Decisions (ADR log)
status: Current
last-verified: 2026-09-18
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
Python (`python/harness/skills/`) and persist in `agent-memory.db`. Instructions
are data, not a security boundary; permissions and the tool allowlist are
enforced in code on the composed `AgentConfig`. The learning engine only creates
inert candidates; promotion to an active skill is explicit, evaluated and
operator-gated.
**Why:** Duplicate infrastructure and autonomous self-modification are forbidden,
and prose cannot be a security boundary.
**Impact:** Additive Phase-3 tables in `agent-memory.db` (idempotent, no manual
migration). Runtime skills live under `python/harness/skills/library/`, distinct
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
**Decision:** Web search/page fetch return a structured RetrievalDiagnostic (provider, category, HTTP status, latency, timeout, result count, bytes, parse outcome, retryability) rather than an opaque UNAVAILABLE; a JSON source document is accepted instead of rejected as 'not HTML'. Structured retrieval is one route among several: a direct SEC EDGAR source (tier primary, US issuers, identity-gated) and an operator-configurable second search provider (vault keys SEARCH_API_CONFIG/SEARCH_API_KEY) join the keyless DuckDuckGo default, with the source policy as data in etrieval/planner.py (inancial_statements → [SEC, JDDS, WEB]). The loop retries only transient failures with bounded backoff, switches to the next independent provider, targets unresolved legs, and records a stopReason. Skill learning stays operator-gated and automatic promotion remains blocked.
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

