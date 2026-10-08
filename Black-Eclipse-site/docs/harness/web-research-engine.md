---
title: Evidence-Driven Web Research Engine
status: Current
last-verified: 2026-10-07
---

# Evidence-Driven Web Research Engine

**Who this is for:** anyone working on research, web retrieval, evidence,
citations, conflict handling or point-in-time correctness in Eclipse.

> Deciding whether a task belongs here, in the browser, or in computer-use? See
> [`research-surfaces.md`](./research-surfaces.md) — the one "which surface answers
> which question" page.

## Why this exists

Eclipse is a financial/engineering agentic harness. Financial analysis demands
*evidence*, not plausible prose. The web research engine exists so the agent can
research the open web and still answer with verifiable, timestamped,
provenance-tracked evidence — and can say precisely what it does **not** know.

The one rule everything follows:

> **The LLM must reason over evidence. The LLM must never be the source of truth.
> Search results are not evidence.**

A search result is a *pointer* (title + URL + snippet). Only a fetched,
normalized, provenance-tracked, timestamped artifact becomes `Evidence`.

## Where it lives

```
python/harness/research/
  web_contracts.py   — the data contracts (Evidence, Claim, Citation, Conflict, …)
  web_intent.py      — deterministic intent classification + routing requirements
  web_planner.py     — deterministic decomposition into sub-questions + queries
  web_providers.py   — SearchProvider protocol + ordered registry + fallback
  web_sources.py     — source typing, entity resolution, ranking, news dedup
  web_freshness.py   — five timestamps + point-in-time admissibility
  web_extract.py     — fetch → evidence, segmentation, structured extraction
  web_browser.py     — browser escalation (reuses the Browser Runtime)
  web_verify.py      — source comparison, conflict detection, claim verify, citations
  web_security.py    — UntrustedContentBoundary + SSRF/URL guard
  web_store.py       — EvidenceStore on the ONE agent-memory connection
  web_engine.py      — ResearchEngine orchestration + status/cancel/continue
  web_coverage.py    — layered sub-question coverage (semantic → idf → keyword)
  web_pricing.py     — honest provider cost ledger (unknown ≠ 0)
  web_graph.py       — evidence-anchored entity/relation extraction
  web_tools.py       — the read-only tools on the ONE ToolRegistry
  web_finance.py     — deterministic financial metrics (adapter over finance_facts)
  web_quality.py     — the internal research-quality score
```

The HTTP surface is `python/harness/routers/research.py` (`/research/web/*`,
operator-gated). The engine is registered in `service.py`; the tools are in
`agents.py` as `WEB_RESEARCH_TOOLS`.

## The pipeline

```
question
  → intent classification          (web_intent)
  → research mandate               (web_contracts.WebResearchMandate, persisted)
  → research plan                  (web_planner: bounded sub-questions + queries)
  → provider registry              (web_providers: ordered, health-aware, fallback)
  → search                         (web_search / news / academic / image / video)
  → extract                        (web_extract / page_extract / pdf_extract)
  → browser escalation             (web_browser, only when extraction is insufficient)
  → normalize + entity resolution  (web_sources)
  → EvidenceStore                  (web_store, on agent-memory.db)
  → freshness / point-in-time      (web_freshness)
  → source ranking                 (web_sources.rank_source)
  → source comparison              (web_verify.compare_sources)
  → conflict detection             (web_verify.detect_conflicts)
  → deterministic calculations     (research.calculations, reused)
  → claim verification             (web_verify.verify_claim)
  → citation generation            (web_verify.build_citations)
  → citation validation            (web_verify.validate_citations)
  → coverage + stopping            (web_engine)
  → synthesis + snapshot           (EngineResult, WebResearchSnapshot)
```

## The Evidence contract

`web_contracts.Evidence` is the most important object. It carries: source
identity + type + publisher, `entityId`, five timestamps (`publishedAt`,
`updatedAt`, `effectiveAt`, `knownAt`, `retrievedAt`), document/page/section,
`rawText` (always preserved), `structuredValue`/`unit`/`period`, `contentHash`,
`confidence`, `provenance`, and `contentTrust` — always `UNTRUSTED`.

## Five timestamps (never conflated)

| field | meaning |
|---|---|
| `publishedAt` | when the issuer published it |
| `updatedAt` | when the issuer last revised it |
| `effectiveAt` | when the described fact takes effect |
| `knownAt` | when the fact became knowable (publication, else retrieval) |
| `retrievedAt` | when this engine fetched it |

**Point-in-time research is mandatory for the financial architecture.** A source
whose `knownAt` is after the requested cutoff is never used. A strict cutoff with
an **unknown** time fails closed (the source is rejected, not admitted) — see
`web_freshness.is_admissible_at`.

## Source typing + ranking

`web_sources.classify_source_type` maps a domain to one of the `SourceType`
vocabulary (official filing, government, regulator, company, IR, academic,
financial data, news, industry, analyst, blog, social, forum, wiki, unknown) and
`authority_for` gives primary/secondary/tertiary. `rank_source` scores a source
for a research type with explainable components (authority, primary status,
relevance, freshness, completeness). Financial research ranks SEC/regulators/
filings/IR/financial-data/news/analyst above general web and social. The score is
an internal ordering signal; user-facing output never claims precision from it.

## News deduplication

`web_sources.dedupe_news` fingerprints titles and content hashes and groups
syndicated copies into `SourceFamily`s. Ten sites repeating one Reuters story are
**one** source family, not ten independent sources. Independent-source counts
exclude syndicated copies.

## Conflict handling

`web_verify.detect_conflicts` groups evidence by `(metric, period)`. A difference
is never averaged away: the engine names whether it comes from a different
period, currency/unit, accounting basis (GAAP/non-GAAP), estimate-vs-reported, a
revision, or a genuine conflict. `EXPLAINED` vs `UNRESOLVED` and `MATERIAL` flag
which disagreements the final answer **must** disclose.

## Claim verification + citations

`web_verify.verify_claim` returns one of `SUPPORTED`, `PARTIALLY_SUPPORTED`,
`CONTRADICTED`, `UNSUPPORTED`, `OUTDATED`, `AMBIGUOUS`, `CALCULATED`, `INFERRED`,
with the reason. A claim with no evidence is `UNSUPPORTED`; a claim whose only
support is stale is `OUTDATED`; a claim touching an unresolved material conflict
is `CONTRADICTED`. `build_citations` produces claim → evidence → source →
location; `validate_citations` proves every material claim is traceable.

## Deterministic calculations

Critical metrics are never computed by the model. Where two reported periods for
a metric exist, `web_engine` reuses `research.calculations.period_change` (and the
other Phase-4 calculators) in pure Python and records a `CALCULATION` claim whose
`inputEvidenceIds` are the source evidence. A calculation that cannot be performed
honestly is dropped, never fabricated.

### Financial metrics (`web_finance` + `finance_facts`)

The finance tools give the model deterministic financial math with full provenance
— it never computes a critical metric itself. Three groups, one calculator each
(never a parallel implementation):

- **Ratios / margins / returns** — `finance_metrics` → `finance_facts.metrics.derive`.
  P/E, forward P/E, PEG, P/B, P/S, EV/EBITDA, FCF yield, dividend yield, ROE, ROA,
  **ROIC**, gross/operating/net margin, debt/EBITDA, D/E. Each records formula +
  inputs + sources. A metric whose required input is missing is **refused**, never
  defaulted (e.g. ROIC requires a stated tax rate). The refusal names the exact
  missing input and its remedy (retrieve it via `web_extract`, or pick a metric
  whose inputs exist) — this is a by-design invariant, not a limitation to fix.
- **Risk / return time-series** — `finance_series` → `research.calculations`.
  Sharpe, **Sortino**, **historical VaR**, **beta**, CAGR, volatility, max
  drawdown, period change.
- **Valuation** — `finance_valuation` → `finance_facts.valuation`. **WACC** (CAPM
  cost of equity + after-tax cost of debt; a levered firm must supply cost of debt
  and tax rate) and **DCF** (explicit forecast + exactly one terminal method:
  Gordon growth OR an exit multiple). A WACC/DCF is an **estimate**, every
  assumption recorded, no rate defaulted.

`finance_metric_catalog` lists every metric with its formula.

### Research-quality score (`web_quality`)

A composite, **explainable** and **internal** score over components the engine has
already established: source authority, primary coverage, evidence coverage, claim
support, freshness, conflict resolution and citation coverage. Every component's
raw value, weight and contribution is returned. It drives the
`COMPLETE`/`SUFFICIENT`/`NEEDS_MORE_RESEARCH` decision and is **never** presented
to a user as truth — the output carries that disclaimer. Available via
`research_quality`.

## Security — the UntrustedContentBoundary

Every fetched byte is UNTRUSTED DATA. `web_security.UntrustedContentBoundary.wrap`
delimits content as data and classifies instruction-like signals; the model may
reason *about* it but must never obey it. `web_security.validate_url` is the
offline-safe SSRF guard (scheme, credentials, blocked suffixes, private IP
literals); DNS resolution and redirect revalidation are enforced by the TS
transport (`safeGet`) the bridge calls.

Adversarial pages are still **preserved as evidence** (we do not hide what a
source said), but `web_engine` never launders injected text into a finding: a page
carrying instruction-like content becomes an `UNCERTAINTY` claim, not a `FACT`.

## Budget, status, cancellation, resumability

`ResearchRequest` carries `maxQueries`/`maxSources`/`maxTimeSeconds`/`maxCost`.
`ResearchEngine` emits `webresearch.*` events for observability and keeps a
process-wide status/cancel map (bounded to 256 runs, terminal-first) so a run
started by one tool call can be observed (`research_status`), cancelled
(`research_cancel`), continued (`research_continue`) or updated incrementally
(`research_update`). Every run writes an immutable `WebResearchSnapshot` to
`agent-memory.db`.

### Parallel search

Independent planner queries run concurrently in a bounded pool
(`MAX_CONCURRENT_SEARCHES = 4`), mirroring the concurrent fetch pool
(`MAX_CONCURRENT_FETCHES = 4`). Results are merged deterministically in query
order, so the evidence set never depends on completion order, and a cancel
observed during search still stops the run honestly. Provider rate limits are
respected by the bound.

### Long-running tools and the timeout ceiling

The harness bounds every tool call. For a **long-running** tool
(`ToolDefinition.long_running`), the agent's generic `toolTimeoutMs` ceiling is
NOT applied — the tool's own declared `timeout_ms` is authoritative (still clamped
to the global `TIMEOUT_CEILING_MS`). `research_query`, `research_continue`,
`research_update` and `web_extract` set this flag; each owns an internal deadline.

`ToolRegistry.execute` resolves the effective timeout and writes it to
`ToolContext.tool_timeout_ms`. The engine reads it and **sizes its own budget below
the ceiling** (`_budget_under_tool`), so a deep run returns a bounded partial
result instead of being killed by the harness.

### Incremental research is non-destructive

`update_research` never deletes prior evidence. It re-runs, upserts by
content-derived id (idempotent), appends a NEW snapshot (history preserved), and
returns a **delta** (sources added/changed/dropped, evidence added/removed). The
snapshot chain is the audit trail of what Eclipse knew at each time.

### Bounded payloads

The `EvidenceStore` keeps the full `rawText`, but the model-facing tool payload
and the HTTP API return it bounded (8k chars, with `rawTextTruncated`/`rawTextChars`
flags). Snapshots returned by the API are bounded the same way.

### Cross-run identity (many-to-many)

A source/evidence artifact is IDENTIFIED by its URL/content (`sourceId`,
`evidenceId`) but BELONGS to one or more research runs. Membership is an explicit
many-to-many link table (`WebResearchSourceLink`, `WebResearchEvidenceLink`), so
the same URL fetched in two runs is attributed to both and never clobbered. A
one-time, marker-tracked backfill (`WebResearchMeta`) migrates legacy rows. Per-run
claim / citation / conflict ids are namespaced by `researchId` so they never
collide. `list_evidence` coerces NULL/partial legacy columns to honest defaults, so
`Evidence(**row)` can never crash a tool.

### Cancel / continue

`execute_research` honors a cancel requested before it runs (create → cancel →
execute). `continue_research`/`update_research` clear the cancel event first, so a
resume after a cancel is not instantly cancelled again.

## What is deliberately NOT here

- No second search-provider chain: `web_providers` wraps the existing bridge
  capability, which already contains the multi-provider fallback.
- No second browser: escalation calls the existing `BrowserManager`.
- No second transport, HTML/PDF parser, memory, tool registry or agent loop.
- No model as a source of truth, no fabricated values, URLs, citations or dates.

## Surfacing, autonomy, and search-provider ergonomics

- **Chat Sources panel.** The web-research tools route each fetched evidence item
  and each detected conflict into the run's `source_sink`
  (`source_collector.add_web_source`/`add_web_conflict`), so web provenance renders
  in the SAME chat Sources area the retrieval layer uses — one surface, no new wire
  contract. A failed fetch is a failed route, never a citation.
- **Dedicated Research screen.** The `research` AppTab renders
  `components/screens/research/research-screen.tsx`, a `CustomizableWorkspace`
  over the research widget catalog (`lib/research/research-widgets.tsx`). It lists
  runs, starts background runs, shows live progress, evidence, claims/citations
  and conflicts, and enables a recurring brief in one click (over the existing
  `/jobs` templates). All state flows through the ONE `useResearchScreen` hook →
  `/api/research/*` → Python `/research/web/*`; the widgets never re-implement
  research or fabricate a value.
- **Schedulable research.** Research runs in the background through the existing
  job scheduler via three inert templates: `deep-research-brief` (cron),
  `competitor-watch` (cron) and `research-topic-digest` (interval). Each is an
  ordinary `objective` job on the `eclipse-agent` and passes the same save-time
  guardrails; nothing switches on by itself.
- **Background runs (no blocking turn).** `research_query` runs synchronously
  inside its tool call; `research_start` (and `POST /research/web/start`) plans +
  persists the mandate via `create_research_sync` FIRST, then executes it as a
  background task (`schedule_background_research`). The research id is observable
  immediately and the state is re-persisted on every transition, so
  `research_status`/`research_cancel`/`research_continue` work from any later
  tool call. A finished task leaves its result in the store.
- **Search providers.** `SEARCH_PROVIDER_PRESETS` (Tavily, Brave, Exa, Serper,
  SerpApi, Bing/Azure, Google CSE, SearXNG) each carry a unique `keyEnv`, so a user
  adds a dependable engine by pasting ONE key in the Settings modal — no
  `SEARCH_API_CONFIG` JSON required (`SearchRetrievalSettings` renders a
  vault-backed `ProviderKeyEditor` per provider; keys are encrypted and never
  echoed). `lib/harness/web-provider-resolve.ts` is the ONE resolution rule:
  advanced `SEARCH_API_CONFIG` + `SEARCH_API_KEY` wins; else the first configured
  named provider; else the KEYLESS FALLBACK CHAIN — DuckDuckGo HTML, DuckDuckGo
  Lite, Mojeek, Bing HTML — tried in order, so a single challenged engine no
  longer blanks the search. A live connectivity test is available
  (`/api/search-provider`).
- **JS rendering & paywalls.** A page that is a JavaScript-only shell
  (`javascript_only`), a parse failure, or a subscription/login wall
  (`paywalled`; new diagnostic category in `lib/retrieval-diagnostics.ts`)
  escalates to the existing browser runtime with credentials when available; a
  bare 403 stays `http_error` (bot/geo block) rather than being mislabelled a
  paywall. One-click enablement: `POST /browser/install` installs Playwright +
  Chromium idempotently and reports the binary's true presence; the Settings panel
  and the `/api/search-provider/install` proxy surface it.
- **Structured connectors.** Academic/news/image/video are first-class keyless
  connectors, not keyword hacks. `lib/web-connectors.ts` reaches OpenAlex,
  Crossref, GDELT, Openverse and Wikimedia Commons through the shared SSRF
  transport and normalizes each to `WebSearchResult`. The bridge exposes them as
  `academic_search`/`news_search`/`image_search`/`video_search` capabilities
  (`data-bridge.ts` + the `/api/harness/data` allowlist). The Python
  `web_providers.py` `ConnectorSearchProvider` registers `eclipse_academic`,
  `eclipse_image` and `eclipse_video`; the corresponding tools use their kind and
  fall back to plain web search only when the connector chain is unavailable.
- **Coverage method.** `_answered_questions` is layered and reports which layer
  ran (`coverageMethod`): `semantic` (embedding similarity, when an embedding
  runtime is available), `idf` (IDF-weighted term overlap — answers a
  sub-question only when its DISTINCTIVE terms are corroborated), or `keyword`
  (the conservative any-token fallback). Per-question scores land in
  `questionScores`. It is a coverage signal, never a correctness claim.
- **Cost accounting.** `research/web_pricing.py` gives an honest estimated spend.
  Keyless providers are FREE (known 0.0); a paid provider with no configured
  price is UNKNOWN (None — never 0), so a run total is `exact` only when every
  used provider was priced. Set `HARNESS_WEB_PRICE_<PROVIDER>_QUERY` (and
  `_FETCH`) to enable estimates; `maxCost` is enforced before extraction only
  when the total is exact, otherwise it is disclosed in `coverage["cost"]`.
- **Entity/knowledge graph.** Beyond claim→evidence, `research/web_graph.py`
  extracts an evidence-anchored graph into `WebResearchEntity`/
  `WebResearchRelation`: companies (via `resolve_entity`), proper-noun terms, and
  `metric → value`/co-occurrence edges. Every node/edge carries the evidence it
  came from — `build_graph` emits nothing ungrounded. Surfaced on `EngineResult`
  (`entities`/`relations`), via the `research_graph` tool, the run API, and a
  Knowledge Graph widget on the Research screen.

## Tests

- `test_web_research_unit.py` — intent, planning, provider fallback, normalization,
  extraction, source typing, entity resolution, ranking, news dedup, freshness,
  point-in-time, conflicts, claim verification, citations, injection, SSRF.
- `test_web_research_integration.py` — end-to-end pipelines, tools, cancellation,
  snapshots, registration.
- `test_web_research_tools.py` — browser escalation, PDF honesty, verification tools.
- `test_web_research_api.py` — the operator-gated HTTP surface.
- `test_web_research_hardcore.py` — the NVIDIA investment/competition analyses and
  the adversarial injection case.
