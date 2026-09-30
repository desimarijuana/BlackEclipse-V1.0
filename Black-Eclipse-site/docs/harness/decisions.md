---
title: Harness Decisions
status: Current
last-verified: 2026-09-30
---

# Harness Decisions

Decisions for the harness. Deep architecture ADRs are mirrored in
`docs/DECISIONS.md` (ADR-018) and originate in `skills/ARCHITECT.md`.

## ADR-H1 — The agentic runtime is Python (LangChain + LangGraph)

**Decision.** Agents, tools, model providers, harness events and run
persistence are implemented in Python under `python/harness/`, served by
FastAPI. Next.js does not run an agent loop.

**Why.** The requirement is that the agentic side not be written in TypeScript,
and that it connect every model. Python is where the LangChain/LangGraph
ecosystem and provider integrations live, so "support all models" and
"author agents" become configuration rather than bespoke TS adapters.

**Consequences.** A Python service is spawned and health-checked on first use.
Agent runs are unavailable (503) without it — by design, never degraded to a
fake agent. The earlier TypeScript Phase-1 kernel (contracts + registry +
runtime + adapters) was retired; only input validation, vault resolution, the
proxy and the JDdS bridge remain in TS.

## ADR-H2 — Next.js keeps exactly two jobs

**Decision.** The front door (a) validates input + resolves agent/LLM config
from the vault, and (b) exposes a read-only JDdS data bridge. Nothing else.

**Why.** These are the two things Python cannot own: the encryption vault
(`SystemConfig` + provider keys in `jdds.db`) and Prisma/JDdS access. Resolving
credentials in TS keeps the key out of the Python process except for the single
run it is needed for.

**Consequences.** The TS harness surface shrank from ~20 modules to ~12 small
ones with no agentic logic.

## ADR-H3 — JDdS is reached through a read-only capability bridge

**Decision.** Python tools request named capabilities
(`market_snapshot`, `fundamentals`, `news`, `source_health`) via
`POST /api/harness/data`; `data-bridge.ts` performs the Prisma query.

**Why.** There must be one financial data layer. The Python side still owns the
tool *contract* (name, schema, permission, risk, honesty rules); only the data
access is delegated. The endpoint is guarded (Bearer `CRON_SECRET`) and
whitelists capabilities — it cannot write.

**Consequences.** Adding a JDdS-backed tool means adding a capability on both
sides. No Python code opens `jdds.db`.

## ADR-H4 — Universal model coverage via catalog + OpenAI compatibility

**Decision.** `PROVIDER_CATALOG` declares providers, their LangChain family,
default base URL/model and env var. First-party integrations are native;
everything else uses the OpenAI-compatible protocol (which also covers local
servers).

**Why.** A branch per vendor does not scale and couples the runtime to vendors.
A catalog is data, and the compatible path alone reaches most hosted + local
models, so "all models that exist" is achievable without bespoke code.

**Consequences.** Model metadata is exposed at `GET /api/harness/models`.
Adding a provider is one entry (+ a requirements line for native integrations).

## ADR-H5 — Agent memory lives in its own database

**Decision.** Runs, events, tool executions, agent memory and skills live in
`agent-memory.db`, not `jdds.db`.

**Why.** JDdS is the committed seed snapshot with a monthly-update discipline;
harness state is high-churn operational data. Separation prevents write
contention and keeps the snapshot stable, and gives user/skill data its own
lifecycle.

**Consequences.** Two DB files at the project root; `agent-memory.db*` is
gitignored. No Prisma migration — idempotent DDL on first use.

## ADR-H6 — Read-only tools only in this phase

**Decision.** The Python registry refuses any tool whose permission is not
`read`.

**Why.** The kernel must not be able to move money or mutate state before an
approval path exists.

**Consequences.** A later phase adds explicit approval before non-read tools
become callable.

## ADR-H8 — Agents and prompts are Python-authoritative

**Decision.** Agent definitions and system prompts live in Python
(`agents.py`, `prompts.py`). The front door sends only an `agentId`; the runtime
resolves the full `AgentConfig`, including the prompt.

**Why.** An earlier revision kept a prompt mirror in `src/lib/harness/agent-presets.ts`
while the front door sent that copy — which meant the Python prompt was dead
code and the two could silently drift. One source of truth removes the failure
mode entirely.

**Consequences.** Editing a prompt is a one-file change in `prompts.py`.
`GET /api/harness/agents` proxies the runtime; the TS side caches presets
briefly and validates ids against them. Sending a full `agent` object is still
accepted as an explicit override for bespoke callers, but the normal path is an
id.

## ADR-H9 — Token usage is captured honestly, never estimated

**Decision.** The runtime reads each model response's token usage and persists
`promptTokens`/`completionTokens`/`totalTokens` on the run. When a provider omits
a usage block, the run records 0 and reports itself as not having usage
(`totals.runsWithUsage`), rather than estimating from text length.

**Why.** Token consumption is a financial fact for an operator paying per token,
and providers are not uniform — local Ollama/LM Studio commonly omit usage. The
same rule that makes market data honest (UNAVAILABLE over a fake number) applies
here: an estimate presented as a measurement is a lie.

**Consequences.** Analytics (`GET /usage`, Settings › Analytics) can show totals
and simultaneously state how many runs did not report usage. Adding a provider
requires no change — `_extract_usage` reads the standard LangChain
`usage_metadata` first, then the OpenAI/Anthropic metadata blocks.

## ADR-H10 — A provider-agnostic retrieval layer sits between tools and providers

**Decision.** Agents request an *objective + data type*, never a provider. A
dedicated `python/harness/retrieval/` package (`FinancialRetrievalLayer`) plans
the source(s), retrieves them (cache-aware, possibly in parallel), normalizes,
validates, resolves conflicts, and returns provenance-carrying evidence. Tools
call the layer; the layer is the only place that knows JDdS, yfinance or the web
exist.

**Why.** The Phase-2 objective is "what information do I need → what is the best
source → structured/cache/web/multiple → fresh and reliable?": that is a
decision, and a decision belongs in one explainable place, not scattered across
tools. It also keeps the agent decoupled from any single data source and keeps
JDdS and yfinance as *sources*, not mandates.

**Consequences.** Adding a provider means implementing the `RetrievalSource`
contract and adding its name to the planner — no tool changes. Source-selection
policy is data (`planner.py`), so new data types are new rows. Precise data
types (historical prices, macro series, derived metrics) remove WEB from the plan
entirely: the layer returns `UNAVAILABLE` rather than web-sourcing a number.

## ADR-H11 — One shared in-process retrieval cache, no new database

**Decision.** The retrieval layer caches with per-data-type TTLs in-process.
The runtime owns ONE `RetrievalCache` shared across runs, with in-flight
deduplication keyed per retrieval.

**Why.** Caching is short-lived operational state; `agent-memory.db` stays the
only harness-owned store and no new database is introduced. Sharing one cache is
safe because deduplication is keyed per retrieval: two concurrent runs asking for
the same dataset share a single provider call (the "multiple agents request the
same data" requirement).

**Consequences.** The cache does not survive a process restart — acceptable for
market data, which is re-fetchable. `GET /retrieval/metrics` reports cache
hits/misses/in-flight honestly. A durable cache would need a later ADR.

## ADR-H12 — Web research is one system and precise data is never web-sourced

**Decision.** `src/lib/web-research.ts` is the single web search + page
retrieval implementation, backing both the retrieval layer's `web_search`/
`web_fetch` capabilities and the legacy `search_web` agent tool (which now
delegates to it). The retrieval planner forbids web for `historical_prices`,
`macro_series` and `derived_metric`.

**Why.** A second search system was explicitly forbidden, and using search
results to answer a precise quantitative question (e.g. "AAPL's 5-year Sharpe
ratio") is fabrication by another name. The honesty rule that governs JDdS
(UNAVAILABLE over a fake number) applies to web research too.

**Consequences.** Web evidence always carries provenance
(`source/sourceType/url/title/publishedAt/query/validationStatus`); missing
metadata is `null`, never guessed, and a result that could not be fetched is
marked `unverified` rather than presented as read.

## ADR-H13 — The run streams, and the final step always answers

**Decision.** The agent node streams tokens via `model.astream`, emitting
transient `model.delta` events that reach the UI over SSE but are never
persisted. On the last allowed step, tools are unbound, an in-band instruction
forces a text answer, and any residual tool calls are stripped; a forced turn
that still produces no text fails honestly as `MAX_STEPS_EXCEEDED`.

**Why.** Two real failures drove this. (1) The chat was a blank spinner for up
to ~2 minutes — the user could not tell the agent was working or what it was
doing. (2) A tool-calling model (notably local Ollama models) would loop until
max steps and return `MAX_STEPS_EXCEEDED` instead of an answer, including
hallucinating tools that do not exist; the agent was, in practice, "unable to
answer" research questions. Unbinding tools alone was insufficient — the model
kept emitting tool calls from the conversation's momentum — so the fix is
threefold: unbind, instruct in-band, and strip residuals.

**Consequences.** Token deltas are high-frequency and worthless after the run,
so they ride the bus and are not written to SQLite; the persisted trace still
ends with the full `model.completed`. The front door can start a run in the
background and relay its stream; a streaming failure falls back to the one-shot
route, so a run always yields an answer or an honest error. `GET
/retrieval/metrics` and the per-run event trace remain the source of truth for
what actually happened.

## ADR-H14 — Checkpoints and git workflow live in the front door

**Decision.** Conversation checkpoints (`src/lib/chat/checkpoint-store.ts`) and
the git workflow (`src/lib/git/service.ts`) are Next.js front-door features, not
Python-runtime ones. Checkpoints are JSON snapshots under the session folder;
git runs through `execFile` with argument arrays, refuses secret-looking staged
paths, and never force-pushes.

**Why.** Both are filesystem/process concerns, and the Python runtime is
deliberately read-only with no filesystem access. Keeping them in the front door
preserves that boundary. The git service must run against the real repo root
(paths from `git status` are repo-relative), which is why it resolves the root
once rather than assuming the app's cwd.

**Consequences.** Chat state lives in the browser, so checkpoint save/restore is
client-driven (the server only stores snapshots). `push` is always a separate,
explicit action from `commit`; there is no auto-commit or auto-push.

## ADR-H15 — Evidence-grounded answering is one shared, deterministic research flow

**Decision.** Phase 4 adds a single shared package `python/harness/research/`
that turns an objective into a typed **research mandate**, retrieves each fact
leg through the *existing* Financial Retrieval Layer, produces deterministic
per-leg **coverage**, validates structured **claims** against actual evidence,
computes named metrics in **pure Python**, and persists a bounded **research
receipt**. It adds no agent loop, no model adapter, no second retrieval system
and no second database.

**Why.** Retrieval/provenance (Phase 2) were stronger than final-answer
enforcement: nothing turned a user objective into required facts, checked each
was covered by admissible evidence, or gated the model's citations. A shared
flow is reusable by every current and future financial agent (and, later, by
visual-workflow nodes) instead of each agent rebuilding its own citation logic.

**Consequences.** The model interprets and explains; the harness owns retrieval
policy, evidence identity, coverage status, calculation truth, structural
validation and the accept/partial/reject decision. Unsupported/general chat is
unchanged — it classifies as `general` and continues on the existing path.

## ADR-H16 — Coverage is per fact leg; successful retrieval is not coverage

**Decision.** Coverage is computed per mandate leg as `covered`, `conflicting`,
`unavailable`, `unknown` or `not_applicable`. A leg is `covered` only when
evidence matches identity, metric, period, consolidation basis and unit/currency.
HTTP/tool success, search snippets, planning responses, stale cache and ambiguous
identity never satisfy a numeric leg.

**Why.** A single global "did it work" boolean (or trusting a 200 response)
lets a wrong-period or wrong-entity row masquerade as an answer. Claim-aware
coverage lets a valid revenue comparison coexist with an explicitly unsupported
causal explanation.

**Consequences.** Partial answers are first-class: material gaps survive to the
answer and receipt rather than being silently dropped.

## ADR-H17 — The answer gate is deterministic; semantic support is reported, not asserted

**Decision.** The validator deterministically checks evidence-ID existence,
entity/metric/period/basis/unit/currency compatibility, derived-claim
calculation registration, conflict visibility, point-in-time admissibility and
citation-URL provenance. It never claims to prove semantic entailment: where
meaning cannot be checked deterministically a claim is `needs_review` and
presented as unverified. The model may not be the sole gate.

**Why.** ID validation is checkable; "does the evidence *mean* the claim" is
not, reliably, without a labeled evaluation set. Claiming perfect verification
would itself be a fabricated confidence signal — the same dishonesty rule that
governs market data.

**Consequences.** One bounded repair round may be attempted with the exact
invalid claims; if still invalid the claims are stripped/qualified and a useful
partial result is returned.

## ADR-H18 — Point-in-time cutoffs are explicit and enter cache identity

**Decision.** An optional `asOf` on the mandate/request excludes evidence with
`publishedAt > asOf` and participates in the retrieval cache/durable key. The
five temporal concepts are kept distinct: `period`, `dataTimestamp`,
`publishedAt`, `retrievedAt`, `asOf`. An unknown publication time stays unknown
and is never inferred from the fiscal period, retrieval time or a current page.

**Why.** Point-in-time analysis is only honest if availability is known;
inferring it silently (or reusing an uncutoff cached result) would corrupt both
the answer and the audit trail.

**Consequences.** `NormalizedFinancialObject` gains additive optional `basis`
and `publishedAt` fields; existing providers leave them `None` rather than
guessing. Schema changes are additive/idempotent.

## ADR-H19 — Calculations are pure functions with auditable inputs

**Decision.** `research/calculations.py` implements period change, CAGR,
annualized volatility, maximum drawdown and Sharpe as pure functions that record
calculation id/version/formula, input evidence ids + identity, date window,
observation count, frequency, missing-data policy, units/currency, annualization,
risk-free source and assumptions. They reject mixed identities, undocumented
duplicate dates, insufficient observations, non-finite values and missing
assumptions; they never interpolate or backfill. Sharpe requires an explicit
risk-free rate.

**Why.** A number the model reasons out in prose is unauditable. A deterministic
module makes the result reproducible and its limitations explicit.

**Consequences.** Results are returned as `derived` evidence, never reported
facts, and carry input references for the receipt and citation metadata.

## ADR-H20 — Identifiers are content-sensitive cryptographic digests, never `hash()`

**Decision.** Evidence receipt hashes and calculation ids are derived from a
canonical JSON serialization via SHA-256 (`research/ids.py`), not Python's
salted built-in `hash()`. An evidence digest includes the item's content and
provenance; a calculation digest includes version, formula, inputs, window,
assumptions and value.

**Why.** `hash()` is salted per process, so a stored receipt's hash was neither
reproducible across restarts nor content-verifiable, and two different facts
could share an id. Determinism is the point of an audit artifact.

**Consequences.** Identifiers are stable across processes (tested by spawning a
fresh interpreter) and distinct values for the same dates never collide.

## ADR-H21 — A supported request is gated before the agent graph and never downgraded

**Decision.** `execute_run` classifies the objective first. An unambiguous
single-entity, two-period `financial_comparison` is routed into the research flow
*before* the ordinary agent graph, so no duplicate retrieval or contradictory
answer occurs. A model or synthesis failure yields an honest partial/rejected
result rather than falling through to an ungated model answer.

**Why.** Running both paths would double retrieval and risk two conflicting
answers; silently falling back would defeat the entire evidence gate on exactly
the requests it exists for.

**Consequences.** The classifier is deliberately strict — `supported` requires
one entity, two periods and no ambiguity; company-vs-company or vague "growth"
asks continue on the existing path. Synthesis receives only the mandate, a
bounded evidence packet and coverage (no tools, no memory).

## ADR-H22 — Semantic support is evaluated, not asserted; production stays `needs_review`

**Decision.** A versioned, human-labeled evaluation set
(`research/eval/dataset_v1.json`) measures citation correctness and semantic
support separately. The judge never sees the gold label. Production claim status
remains `needs_review` unless the deterministic checks pass and the support
policy permits otherwise. If a model critic is added it is advisory only, and its
precision/false-accept rate is reported against human labels.

**Why.** Citation existence does not prove entailment. Reporting an evaluation
number honestly — including false accepts — is the only way to avoid claiming a
truth guarantee the system cannot provide.

**Consequences.** The evaluation runner (`python -m harness.research.eval`)
reports counts, confusion matrix, false accepts/rejects and per-slice results,
and can never set a claim to verified on its own.

## ADR-H23 — Bounded web escalation when structured evidence cannot answer

**Decision.** The research flow escalates a still-unsatisfied statement leg from
structured sources to trusted web sources through a fixed hierarchy — primary
(SEC/company IR/regulators), then bounded reputable secondary — via the existing
`web_search`/`web_fetch` bridge. Escalation is targeted (only unsatisfied legs),
bounded by one `ResearchBudget` (searches/fetches/pages/time/tokens), and every
numeric web fact must pass a DETERMINISTIC validator (`web_facts.validate_fact`)
before it becomes evidence.

**Why.** Structured providers legitimately do not cover everything (e.g. the
JDdS statement snapshot may lack a requested year), and stopping there produced
unhelpful "not established" answers. But "answer anyhow" must never become
"invent": a search snippet is not a number, a page instruction is not a fact, and
the model cannot be the authority on whether a source supports a value.

**Consequences.** A fact is accepted only when its page was fetched this run, its
`sourceSpan` is a verbatim quote from that page, the value appears in the span,
the span does not state a conflicting fiscal period, and metric/period/currency/
basis match the mandate leg. Secondary sources are labelled and shown as lower
confidence. Budget exhaustion is recorded in the receipt with the attempted
paths. This added no second search system and no second data plane.

## ADR-H24 — Distinct coverage statuses, and missing basis qualifies rather than fails

**Decision.** Coverage reports distinct statuses — `covered`, `qualified`,
`conflicting`, `no_matching_period`, `stale`, `unavailable`, `unknown` — instead
of collapsing them into a generic `unknown`. A required consolidation basis that
the source does not state makes a leg `qualified` (the issuer-reported value is
present and presentable with disclosure), not `unknown`/`unavailable`.

**Why.** The earlier gate mislabeled "there is a revenue row but for FY2019" and
"the basis is unconfirmed" identically, which produced misleading diagnostics and
blocked otherwise-valid facts. A missing *blocking* field (identity, currency)
still fails; a missing *qualifying* field (basis, unit) is disclosed.

**Consequences.** The answer can present independently validated figures while
naming exactly what is unconfirmed, and a conflict or missing period never
prevents other verified facts from being returned.

## ADR-H25 — Web retrieval failures are structured diagnostics, not opaque UNAVAILABLE

**Decision.** Every web search and page fetch returns a `RetrievalDiagnostic`
(`src/lib/retrieval-diagnostics.ts`): provider/transport, normalized status,
failure category (`zero_results`, `transport_error`, `timeout`, `blocked`,
`http_error`, `content_type_rejected`, `parse_failure`, `not_configured`,
`invalid_request`), HTTP status, latency, timeout state, result count, bytes,
parse outcome, and retryability. A JSON source document (e.g. a SEC XBRL
endpoint) is accepted and returned as raw text rather than rejected as
"not HTML". Diagnostics flow through `SourceOutcome` → `FinancialRetrievalResult`
→ the engine/receipt. A bounded `research_health` capability probes each route.

**Why.** The Phase-5 NVDA run could not tell "the web had nothing" from "every
transport is broken". The root cause was three opaque collapses: DuckDuckGo's
HTTP 202 anti-bot page parsed to zero results and returned `[]`; a valid
`application/json` SEC response was rejected by a content-type gate; and
`escalation.py` inspected only `status == "OK"` and discarded the reason.

**Consequences.** "search returned zero results" is now distinct from "request
failed / timed out / was blocked / page fetch failed / HTML could not be parsed",
and the receipt says which. No secrets or full response bodies are recorded.

## ADR-H26 — Independent source routes with a deterministic, testable policy

**Decision.** Structured retrieval is one source among several, not the only
path. A direct **SEC EDGAR** source (`SecFilingsSource`, tier `primary`, US
issuers) and a **second, operator-configurable web-search provider**
(`CustomJsonSearchProvider`, credentials from the settings vault via
`SEARCH_API_CONFIG`/`SEARCH_API_KEY`) join the keyless DuckDuckGo default. Source
selection is explicit data in `retrieval/planner.py`:
`financial_statements → [SEC, JDDS, WEB]`. Every provider implements the existing
`RetrievalSource` contract and can be disabled/replaced independently.

**Why.** All four web routes in the failed run shared one transport; a second
route that depends on the same search call is not independent. The operator
asked to be able to add any search API, so the provider is a generic
configurable JSON adapter, not a hard-coded vendor. SEC is a direct filing
route, not a web search, so a numeric fact never originates from a snippet.

**Consequences.** `sec_filings` routes through the shared identity gate (a bare
ticker cannot answer for the wrong issuer). `not_covered` is returned for non-US
issuers. A missing credential reports the capability as unconfigured and the run
continues with the remaining providers. No second data plane and no second
search system.

## ADR-H27 — The research loop retries transiently, switches providers, and keeps going

**Decision.** The retrieval layer retries only *transient* outcomes (timeout,
transport, 5xx, 429) with bounded deterministic backoff (`retrieval/retry.py`)
and never retries a permanent one (blocked, unsupported content type). The engine
records per-leg retrieval status + coverage status + diagnostics, switches to the
next independent provider on failure, targets only unresolved legs in escalation,
preserves every already-verified leg, and stops only when coverage is complete,
the budget is exhausted, or every route failed — recording the `stopReason`
(`all_required_legs_resolved` / `budget_exhausted` / `provider_routes_unavailable`
/ `unresolved_facts_remain`).

**Why.** "Keep trying independent methods and return every verifiable part"
requires the loop to distinguish a transient blip from a missing fact, and to be
explicit about why it stopped. A stale snapshot must never satisfy a fresh-data
requirement, and an unrelated period must not be relabelled as a gap in the
requested period.

**Consequences.** A partial run returns its verified facts plus the failed routes
and the exact unresolved facts. `legStatus` and `stopReason` ride the receipt and
the `client.final` answer. No unbounded looping: retries and escalation are
bounded by `ResearchBudget`.

## ADR-H28 — Skill learning stays operator-gated; Phase-6 candidates deferred

**Decision.** Phase 6 does not change the skill lifecycle. Automatic promotion
remains blocked; candidates remain inert, reviewable records. Capturing richer
failure/source-selection diagnostics that could seed a linked skill candidate is
deferred to a follow-up; the diagnostics this phase produces are the evidence
such a candidate would cite.

**Why.** The brief requires the control be preserved (never let the agent
silently edit/enable/promote its own skills). Adding candidate generation without
the review/promotion test suite would risk weakening that guarantee.

**Consequences.** No live behavior depends on candidate generation; the existing
`python/tests/test_skills_*` suite continues to prove unreviewed candidates
cannot affect a run.

## ADR-H29 — Coverage is a capability matrix, not a country list

**Decision.** `get_coverage`/`get_capability_matrix` report, per market, separate
axes: recognition, searchable universe size, quote, history, fundamentals,
official filings, web/documents, observed health, and whether a live smoke check
has run. Each axis distinguishes implemented+configured / implemented but
unconfigured / not implemented / recognized-only. Statements are never implied by
working quotes.

**Why.** The old flat list gave 31 countries the same asset classes and the same
four data types, so a Taiwan request looked as statement-capable as a US one —
which was false. It also told the agent to STOP when a market was absent from the
list (or when JDdS lacked a ticker), even though another provider or source might
answer.

**Consequences.** The tool text now instructs the agent to exhaust eligible
routes (live providers → official filings → bounded web) before concluding
evidence is unavailable, and to treat a missing universe row / unconfigured
capability as a routing fact, not a stop signal.

## ADR-H30 — Instrument identity is global and suffix-aware; an unknown suffix is never guessed

**Decision.** A recognised exchange suffix (`.TW`, `.KS`, `.SA`, `.L`, `.T`, `.NS`,
…) is split into an implied market, and the vault is queried for BOTH the bare
local code and the suffixed form. Only an explicit, curated suffix table is
recognised; an unrecognised suffix is left intact (no guess), and a genuinely
ambiguous bare ticker still asks for the market.

**Why.** The JDdS master stores instruments under bare local codes (`2330`,
`005930`, `PETR4`) while users overwhelmingly type the Yahoo-style suffixed form;
the suffixed string never matched and returned `not_found`, so a Taiwan/Korea/
Brazil instrument was reported "not in the universe" though it existed.

**Consequences.** `resolveVaultInstrument` is the single place this happens, so
every resolving capability benefits. `splitExchangeSuffix` is mirrored in Python
(`infer_market_from_symbol`) for routing eligibility only; canonical identity
remains the TS instrument master.

## ADR-H31 — Providers are gated by eligibility, and the fetch transport uses a declared UA

**Decision.** A provider declares eligibility for a request's market/issuer type
and is SKIPPED when ineligible (`SecFilingsSource.eligible` — SEC for non-US
issuers), rather than attempted and reported as an outage. The shared fetch
transport sends a declared, email-contact `User-Agent`; SEC's fair-access policy
requires an email-shaped contact (verified: a URL-only UA is rejected 403).

**Why.** The TSMC run attempted SEC for a Taiwanese issuer and recorded "SEC
bridge HTTP 400" — a predictable ineligibility misread. And every non-US fetch
returned UNAVAILABLE because the transport spoofed a browser UA, which SEC,
`www.sec.gov`, TSMC IR and `pr.tsmc.com` all reject with 403; a declared
email-contact UA receives 200 from all of them (verified both ways).

**Consequences.** A missing credential disables only its route; routing continues.
Documents are content-negotiated: JSON/XML/XBRL/text pass through as raw text and
text-PDFs are extracted, while a scanned/image PDF or a JavaScript-only shell is
reported with a distinct category (`unsupported_document` / `javascript_only`),
never returned as garbage.

## ADR-H32 — Health is keyed by route; learning candidates carry diagnostics and scope

**Decision.** Source health is keyed by `(source, market, assetClass)` — the
dimensions that identify a route — and a declared target with zero attempts is
`unknown`, never healthy or failing. Learning candidates created from a run carry
that run's structured failure diagnostics and the observed regional/provider
scope; candidates remain inert and promotion stays operator-gated.

**Why.** The old aggregation collapsed recorded runs to `(market, assetClass)`
and copied the single aggregate onto every declared provider row, so
`JDDS (US, equity)` and `JDDS (US, etf)` reported the same counter and two
providers reported each other's numbers. And a lesson drawn from one country's
failure must not be generalized to "all countries".

**Consequences.** The Skills UI shows the affected scope and linked diagnostics;
an unreviewed candidate cannot influence live behavior (regression-tested).

## ADR-H33 — Memory/skills DB path is repo-rooted; legacy stores reconcile non-destructively

**Decision.** `eclipse-memory.db` (and `agent-memory.db`) default to the
repository root (`Black-Eclipse-site/`), NOT the process working directory;
`ECLIPSE_MEMORY_DB_PATH` / `AGENT_MEMORY_DB_PATH` remain explicit overrides.
`GET /health` reports the resolved path plus a non-secret identity (path hash).
On open of the stable default, a one-time non-destructive reconciliation copies
rows forward from a legacy `<cwd>`/`python/` database when the stable one is
empty, using `INSERT OR IGNORE` and never touching the source.

**Why.** The runtime is spawned from the repo root, but a manual `uvicorn
--app-dir python`, a pytest run, or any tool started from `python/` resolved a
different file. The repo held TWO `eclipse-memory.db` files (root: memories +
skills; `python/`: skills only), so a runtime launched from a different cwd read
and wrote a different memory store.

**Consequences.** One stable application-data location across launch dirs; a
mismatch is observable in health. A source database is never deleted or
overwritten; a populated stable database skips reconciliation entirely.

## ADR-H34 — Explicit memory intent is detected deterministically, never auto-published

**Decision.** Explicit user phrases ("remember this", "save this preference",
"always do X", "for this ticker", "forget this", "correct this", "turn this into
a skill") are detected by a deterministic classifier (`eclipse_memory/intent.py`)
before the model turn, independent of whether the model calls the `memory` tool.
Clear, safe saves/forgets/corrections are written through
`EclipseMemoryService`; refusals (secrets/credentials, sensitive identifiers,
raw dumps, policy-override attempts) and unclear scope are NEVER written.
Forget/correct archive/supersede — never hard-delete.

**Why.** Normal chat relied on the model voluntarily calling `memory`; durable
preferences stated in plain language were often lost. Auto-capture was disabled
by default, so nothing deterministic filled the gap.

**Consequences.** Every explicit action emits an auditable `memory.*` event and
returns a visible confirmation with scope + inspect/undo links. Automatic capture
remains OFF by default (no auto-capture of every turn); the deterministic path
runs only for explicit intent.

## ADR-H35 — Learning is automatic for eligible runs; drafts carry real procedures

**Decision.** Completed ordinary chat runs (not just skill runs) are analyzed
automatically after the run. Under the current default (`skill_learning_mode:
automatic_selective`) the deterministic, criteria-driven analyzer creates inert
learning candidates without the user asking, and the run's `memory` blob reports
`learningEligibility.autoCaptured` + `learningAnalysis.candidatesCreated` for the
UI. Candidates are deduplicated by signature (bounded queue) and are NEVER
enabled/promoted. A merely eligible run is *not* itself proof of a reusable
procedure: an implicit `successful_procedure` candidate additionally requires
recurrence evidence (the same successful workflow observed in a prior completed
run); a recovered failure or a user correction is strong single-run evidence. An
explicit "turn this into a skill" request creates an inert candidate + draft
through the real persistence path immediately — no second "Learn from this run"
click. Candidate → draft generation produces a complete `SKILL.md` (procedure
steps, typed input/output assumptions, existing safe tools only, source-run
provenance, limitations, evaluation cases) while remaining `status: draft` /
`evaluationStatus: not_evaluated`. When the trace has no evidence for a real
procedure, the draft says so and stays a manual-authoring candidate.

**Why.** Drafts were manifest-only (`instructions: None`), so "turn this into a
skill" produced an unusable artifact; ordinary chat runs could not become
learning candidates; and requiring the user to manually trigger learning meant
successful work routinely never became a candidate. A later selectivity pass
(ADR-H37) showed the opposite failure — treating any eligible run as a skill —
so recurrence was added as the missing evidence gate.

**Consequences.** No automatic skill enablement/promotion/permission expansion —
the hard rule is preserved (the policy `auto_promote_low_risk` stays locked
off). Automatic learning at most creates inert records; a draft is stored as an
inert version and only evaluation + operator approval can enable it. Operators
can disable detection entirely via `skill_learning_mode: off`.

## ADR-H36 — Chat can explicitly invoke an enabled skill as a controlled sub-run

**Decision.** A `skill_invoke` tool lets the model deliberately run ONE enabled,
compatible skill from chat. Execution uses the existing
`SkillExecutionRequest`/`execute_skill` runtime, preserves `parentRunId` and the
trace, enforces the skill's tool allowlist and the default-deny permission policy
in code, and returns the child run's events/results. Discovery (`skill_list` /
`skill_view`) does not equal invocation.

**Why.** The runtime could discover and view skills but ordinary chat had no safe
way to actually run one; pretending discovery equals use was misleading.

**Consequences.** A skill can never widen the agent's tools or grants through
this path; only enabled skills are invocable; the child's `skill.*` events ride
the parent's SSE stream.

## ADR-H37 — One shared memory decision gate; durable memory is opt-in and selective

**Decision.** Every path that can create or alter a durable memory, a
suggestion, a correction/forget action, or a learning candidate passes through a
single server-side decision gate (`python/harness/eclipse_memory/decision.py`)
that returns exactly one of four outcomes:

- `save` — high-value, durable, clearly-intended, safe; persist now;
- `suggest` — possibly durable, but intent/scope unclear; do NOT persist, show a
  quiet Save/Dismiss control (an inert `MemorySuggestion` row);
- `history_only` — relevant to this task/conversation and searchable in
  conversation/run history, but not worth recalling as durable memory;
- `ignore` — low-value, redundant, temporary, unsafe, unsupported or irrelevant.

The gate validates a proposal against the actual user message, identity, scope,
provenance, category, evidence, duplication, sensitivity, policy and privacy
rules. The deterministic explicit-command path (clear "remember/forget/correct")
is always honoured when safe and clear; a casual durable mention is at most a
suggestion. The model-facing `memory` tool may *propose* but cannot authorize its
own write — the gate re-checks it against the user turn, and tool output,
retrieved memory, attached documents and web content are never user intent.
Financial facts (prices, valuations, earnings, predictions, unverified claims)
are never durable memory. Automatic memory capture, automatic candidate
detection and automatic suggestions are controlled by two *mode* keys
(`memory_mode`, `skill_learning_mode`: `automatic_selective` | `ask_before_saving`
| `off`), defaulting to `automatic_selective`; the legacy booleans are derived
from the modes and are neither stored nor settable (migration 7, ADR-H44).

**Why.** The Phase 3-M reliability pass made capture deterministic but too eager:
`auto_capture_enabled`/`auto_candidate_detection` defaulted on, an incidental "I
prefer …" or "Always use X" classified as an explicit save, and the `memory` tool
wrote straight to the service pipeline with no check against the user's actual
words. The result was a database that filled with incidental, task-specific and
occasionally financial text — exactly what a durable memory must not contain.

**Consequences.** One code path authorizes every write, so a new surface cannot
quietly bypass the rules. Explicit controls stay dependable; everything else is
selective and usually `history_only`/`ignore`. A persisted unsafe `true` policy
override is migrated to the safe default (migration 5, recorded in
`MemoryPolicyMigration`) rather than silently continuing the old behaviour. The
storage budget (`max_memories`, default unlimited) fails a new unique save
truthfully as `memory_full` rather than auto-deleting user memory; inert history
does not consume it. The learning path is distinct: a skill candidate is an
on-demand procedure created through an explicit "turn this into a skill" request
or an automatic-selective run with recurrence evidence, never a second memory
note. See ADR-H44 for the mode model that supersedes the per-boolean tuning.


## ADR-H38 — MCP is a user-directed extension surface adapted into the one ToolRegistry

**Decision.** Phase 5 adds `python/harness/mcp/` implementing a local **stdio**
MCP client over the maintained MCP Python SDK, a typed server/effect contract and
threat boundary, collision-resistant namespacing, schema validation, and an
adapter that registers **only selected, read-only** MCP tools into the existing
`ToolRegistry`. There is no second agent loop, tool registry, model adapter or
retrieval system, and MCP results never pass through the native research
verifier. This slice implements gates 5A–5C only; remote HTTP/OAuth (5D), catalog
UX (5E), source-freshness integration (5F), effectful-tool approval (5G),
Eclipse-as-MCP-server (5H), and resources/prompts/subscriptions (5I) remain
future work.

**Why.** MCP must be a user-directed surface — a user may connect a server and
use its tools for any finance workflow, without a finance-domain allowlist and
without JDdS as a mandatory path. But the host still owns execution: launch with
an argv list and no shell, a per-server env allowlist (never the Eclipse
environment/vault/credentials), explicit selection, bounded timeouts/output/
concurrency, cancellation, redaction, and observable events. Routing every call
through `ToolRegistry.execute` means MCP inherits the same validation,
allowlist, read-only enforcement, timeout, persistence and tool-trace as native
tools for free.

**Consequences.** Discovery is not activation: `enabled` defaults False and
`selected_tools` defaults empty, so a discovered tool is inert until named. Only
`read`-effect tools activate; a tool a server does not mark read-only is not
assumed safe — the effect resolves from an operator declaration, then MCP
`readOnlyHint`/`destructiveHint`, else `unknown`. A sanitization collision
appends a stable SHA-256 digest (never a silent merge). Output is bounded and
marked truncated, secrets are redacted, and results carry their server/tool
identity and are labelled external — never Eclipse-verified. `/health` reports
non-secret MCP counts. Turning on a server is explicit operator configuration
(`mcp-servers.json`).

## ADR-H39 — The MCP catalog is operator-reviewed; discovery never activates

**Decision.** Phase 5E adds a catalog API and Settings UI (`GET/POST
/mcp/servers`, `POST /mcp/servers/test`, `DELETE /mcp/servers/{id}`, `POST
/mcp/reload` in Python; `/api/harness/mcp/*` proxies; Settings › MCP Servers) to
add / test / enable / disable / remove local stdio MCP servers and select their
tools. A save reloads the manager in place: only the MCP tools it previously
registered are dropped and re-registered, so native tools are untouched and no
runtime restart is needed. Responses are secret-free — env VALUES are write-only,
and the API returns only env KEY names. Each server carries a versioned
`catalogDigest` (identity + effect + schema) so a changed tool set is reviewable.
Mutations are operator-gated by the same `checkMutationAllowed` rule as every
other mutation; reads are open.

**Why.** The 5A–5C slice was config-file-only: a user had to hand-edit
`mcp-servers.json` and could not see what a server offered, what effect a tool
had, or why a tool was unavailable. That is neither usable nor reviewable. The
phase explicitly requires that newly discovered tools default to disabled and
that users can understand exactly what is enabled and why a call is denied.

**Consequences.** Discovery remains distinct from activation: `enabled` and
`selected_tools` are the only activation inputs, and the panel disables every
non-read/unparseable tool with the reason shown. Removing or disabling a server
revokes its tools on the next reload. Secrets are never echoed; only key names
are shown, and a blank `KEY=` edit keeps the stored value. The whole
`mcp-servers.json` file (which may hold scoped env values) is gitignored.
Effectful-tool approval (5G) is still required before any write/action tool can
be activated — this phase does not weaken that.

## ADR-H40 — MCP trust is explicit: operator-declared effects, confirmed catalogs, transport-authenticated mutations

**Decision.** An MCP server's own metadata is untrusted. Three rules follow:

1. **Effects.** A tool is activatable only when its effect is `read` AND that
   classification is *explicit and reviewable*. An operator `tool_effects`
   declaration is trusted. A server's `readOnlyHint` is untrusted: it can classify
   a tool as `read` for review, but on its own it leaves the tool disabled until
   the operator confirms the current `catalogDigest`. `destructive_hint=True`
   never activates. Only `read` ever activates; `write`/`external_action`/
   `unknown` need the future approval gate (5G).
2. **Catalog invalidation.** A changed tool set, description or schema yields a
   new `catalogDigest`; the previous confirmation no longer matches, so an
   annotation-sourced tool becomes inert again until re-confirmed.
3. **Authorization.** MCP mutations are authorized by *transport* (loopback) or by
   the runtime secret (`X-Harness-Operator`/`Bearer`), never by a JSON
   `operator: true` field. The TS front door still applies `checkMutationAllowed`;
   Python re-checks independently, so a directly reachable runtime cannot be
   handed arbitrary subprocess configuration by spoofing a boolean.
4. **Credentials.** Scoped env VALUES are persisted in the gitignored
   `mcp-servers.json`, written owner-only (0600 where supported). The secure
   settings vault is a TypeScript/Prisma store this Python process cannot read and
   the SDK needs the value to spawn the child; the API returns key names only and
   values are redacted from diagnostics/events/results.

**Why.** A malicious or compromised MCP server controls its own descriptions,
annotations and results. Letting `readOnlyHint` alone enable a tool is a
server-granted permission — the exact thing the product forbids. And a JSON
boolean is not authentication: any client that can reach the runtime could
otherwise configure arbitrary subprocesses.

**Consequences.** A genuinely read-only server still needs one explicit operator
act (declare the effect, or confirm the catalog). The default Eclipse agent can
call selected MCP tools via `allowMcpTools` — an expansion over *registered*
tools only, which registration already gates on enabled + selected + permitted
effect. Custom agents/skills keep exact allowlists. **Limit:** env secrets live in
local plaintext config for now; resolving them from the secure vault through a
secret reference (value never reaching TS/models/events/logs/receipts) is a later
gate. Remote HTTP/OAuth (5D), effectful approval (5G), Eclipse-as-server (5H)
and MCP-aware native source planning (5F) remain future work.

## ADR-H41 — MCP secrets resolve from the encrypted vault; effectful tools require a per-call approval

**Decision.** Two additions close the MCP secret and effect gaps:

1. **Secret references.** A server config may reference a NAMED secret
   (`secret_refs: { ENV_VAR: secretName }`) stored encrypted in JDDS
   (`SystemConfig.key = 'mcp_secrets_v1'`, AES-256-GCM via `connectors/secrets`).
   Only names/masked hints are exposed to the UI. The Python runtime resolves the
   value at child spawn over the authenticated, read-only data bridge
   (`mcp_secret_resolve`); the value is never returned to a browser, the model, an
   event, a log, or a run trace, and it joins the connection's in-memory
   redaction set. Inline plaintext `env` remains supported as the legacy path.
2. **Effectful approvals.** A `write`/`external_action` tool needs (a) the
   operator to enable that effect for the server (`enabled_effects`, default
   `["read"]`) and (b) a valid APPROVED approval for the exact
   `(serverId, tool, argsDigest)`. The digest covers the canonicalized validated
   arguments; a changed payload needs a new approval, a denial is terminal, and
   `unknown` is never approvable. Enforcement is inside the ONE `ToolRegistry`:
   a non-read tool runs only when `ToolContext.authorize_effect` approves THIS
   call; with no authorizer wired, non-read tools are refused.

**Why.** The earlier slice stored scoped MCP env values as local plaintext and
refused every non-read tool with no path forward. Plaintext is not acceptable for
a credential when an encrypted vault already exists, and "there is no approval
flow" is a permanent dead-end rather than a safe default. Both gaps had a
well-scoped fix that reuses existing pieces (the connector crypto, the bridge, the
registry execution seam) rather than a new subsystem.

**Consequences.** A read-only server still stores no secret; a credential-using
server references the vault. Approvals are persisted in `agent-memory.db`
(`McpApproval`) with no secret material and expire (default 15 min). An
unapproved effectful call is refused and surfaces a PENDING request; the operator
decides in Settings. **Limits:** the Python process still receives the resolved
value at spawn (it must, to start the child); the vault key is instance-scoped
(`CONNECTOR_SECRET_KEY` on hosted deployments). Remote HTTP/OAuth (5D),
Eclipse-as-server (5H), MCP-aware native source planning (5F) and
resources/prompts/subscriptions (5I) remain future work.

## ADR-H42 — Remote MCP uses Streamable HTTP with vault-backed auth and an SSRF guard

**Decision.** `MCPServerConfig` gains a `transport` field (`"stdio"` default, or
`"http"` with a required `url`). The HTTP path uses the MCP SDK's
Streamable-HTTP client (`mcp.client.streamable_http`) and shares the *same*
connection lifecycle, discovery, effect/approval gating, output bounding and
redaction as stdio — only the stream source differs. Authentication is a **vault
secret reference** (`auth: {kind: "header"|"query", name, prefix?, secretRef}`):
the token is resolved at connect time over the authenticated bridge, added to the
connection's in-memory redaction set, and never stored in config, returned to the
UI, or logged. Every remote URL passes an **SSRF guard** (Python
`harness/mcp/ssrf.py`, mirrored on the TS side by `checkOutboundUrl`):
https-only (loopback `http` allowed for local testing), embedded credentials
refused, private/link-local/metadata IP literals and private-resolving hostnames
refused, and the check runs BEFORE any outbound connection.

**Why.** "Users can connect anything" is false while only local stdio is
supported — most third-party MCP servers (hosted Google Workspace, Canva, many
financial APIs) are remote. A config-driven outbound connection is also a classic
SSRF vector, and an API token must not be the one secret still stored in
plaintext.

**Consequences.** Header/bearer auth covers the majority of API-key servers
immediately; interactive OAuth (localhost callback, token refresh/clear) is
deferred. `secret_refs` (stdio env) and `auth.secretRef` (http) both resolve
through the same vault. `test_server` refuses an unsafe URL with a diagnostic and
makes no network call. The connection/manager/adapter/approval layer is unchanged
— remote servers reuse the exact same enforcement. Remaining future work:
OAuth lifecycle and TLS/redirect knobs (part of 5D), resources/prompts (5I),
MCP-aware native source planning (5F), and Eclipse-as-server (5H).

## ADR-H44 — Automatic learning is one mode, not several booleans; it saves selectively without prompting
**Decision.** Automatic memory learning and automatic skill learning are each
controlled by a single *mode* key rather than independent booleans:

- `memory_mode`: `automatic_selective` (default) — save strong, durable,
  low-risk, non-sensitive information automatically, without interrupting the
  user; treat one-off requests, temporary task details, generated analysis, tool
  output and changing market data as `history_only`/`ignore`; require recurrence
  for project-specific conventions; a direct user preference is saved on first
  statement. `ask_before_saving` — stage an inert suggestion instead.
  `off` — create nothing automatically.
- `skill_learning_mode`: same three modes, gating automatic learning-candidate
  detection. Implicit `successful_procedure` candidates require recurrence
  evidence; a merely eligible run is not enough. An explicit request always
  creates an inert draft through the real persistence path.

The legacy booleans (`auto_capture_enabled`, `auto_suggest_enabled`,
`auto_candidate_detection`) are now **derived** from the modes: they are neither
stored nor settable, so they cannot drift out of sync. `policy.derived_flags`
projects the modes to the booleans for existing call sites. Migration 7 records
and removes any stored legacy boolean rows so the mode defaults govern.

**Why.** The prior design used three independent booleans whose defaults and
meaning drifted across code, docs, and tests (ADR-H35 said candidate detection
default on; ADR-H37 said all off). A one-flag "fix" left the real product
behaviour wrong in either direction: indiscriminate prompt-after-every-run, or no
learning at all. The intended behaviour is *selective automatic learning* — one
coherent lifecycle with a single source of truth.

**Consequences.** The default is consistent across policy code, persisted
settings, migration, API/UI, tests and documentation. Explicit remember/forget/
correct remain a separate always-on path. The decision outcomes are now
`save`/`suggest`/`history_only`/`ignore` (`run_only` renamed to `history_only` to
name conversation history explicitly). Noisy per-run prompts are removed: the
chat panel shows a learning line only for a genuine automatic capture or an
explicit draft — a merely eligible run shows nothing, and a repeated "Learn from
this run?" confirmation is gone.

**Recurrence is persisted, not window-bound.** Recurrence evidence is stored in
bounded, signature-only ledgers rather than only inferred from the chat-history
window: `MemoryRecurrence` (migration 8, `eclipse-memory.db`) for durable-sounding
statements and `LearningRecurrence`/`LearningRecurrenceRun` (`agent-memory.db`)
for skill-workflow evidence. This closes two limitations: a convention repeated
after the bounded history window is still learned, and implicit skill recurrence
is one indexed lookup that survives restarts (the bounded run scan is only a
fallback, combined with `max`). No raw text is stored, and re-recording the same
run does not inflate the count.

## ADR-H45 — Skill contracts are validated in full, and execution limits are enforced in code

**Decision.** A skill's declared `inputSchema`/`outputSchema` are validated as
JSON Schema documents at registration and evaluation
(`skills/schema_validation.py`, using the already-present `jsonschema`). A skill
OUTPUT is validated against the COMPLETE schema (nested object types, array item
types, enums, `minimum`/`maximum`, `minLength`/`maxLength`, `pattern`,
`additionalProperties`, required fields) — a top-level `required` check alone is
not validation. `status="completed"` and `outputValidated=True` are distinct:
a schema-invalid output keeps `completed` but reports `outputValidated=False`
with a stated warning, never a silent discard. A manifest's `limits.maxToolCalls`
is carried into the run's `AgentConfig` and ENFORCED by the graph — once the
budget is spent, no further tool executes and the run finalizes
(`TOOL_BUDGET_EXCEEDED`).

**Why.** The prior output check only looked at top-level `required`, so a
structurally-wrong nested result could be reported as "validated"; `maxToolCalls`
was advertised in metadata and prompts but never enforced in the loop, so a skill
could exceed its own budget.

**Impact.** New `skills/schema_validation.py`; `AgentConfig.maxToolCalls`;
`TOOL_BUDGET_EXCEEDED` added to the error-code vocabulary (Python + TS);
`jsonschema` declared explicitly in `python/requirements.txt`.

## ADR-H48 — Operator authorization is transport/token proof on every mutation; schema validation fails closed

**Decision.** Every memory/skill mutation endpoint in `main.py` takes the
`require_operator` FastAPI dependency: the caller must originate from loopback
(the front door / local operator) **or** present the runtime secret
(`X-Harness-Operator` / `Bearer`). The body `operator` boolean is read only
afterward, so it can never, by itself, authorize a remote caller. The Next.js
memory/skill clients forward the runtime secret so the front door's trusted
authorization is what reaches Python, matching the MCP endpoints (ADR-H40/H41).
Additionally, full JSON Schema validation FAILS CLOSED: if `jsonschema` is
missing, a declared schema cannot be verified, so `check_schema`/`validate_output`
return failure with an actionable message instead of falling back to a
required-only check that would report partial validation as full. Skill INPUT
validation is pydantic-based and keeps working (structural shape check);
registration/evaluation and OUTPUT validation require the validator.

**Why.** The front door derived `operator` from trusted auth, but the Python
endpoints trusted a body boolean — so a directly reachable runtime (or a crafted
proxied payload) could self-authorize memory writes, policy changes, suggestion
acceptance, skill enablement and promotion. Separately, the `jsonschema`-absent
fallback silently downgraded contract enforcement to a required-fields check.

**Impact.** `main.py` (`require_operator`, applied to all mutation endpoints),
`skills/schema_validation.py` (`check_schema_structural`, fail-closed
`check_schema`/`validate_output`), front-door token forwarding
(`eclipse-memory-client.ts`, `skills-client.ts`), `runtime-config.ts` +
`scripts/doctor.js` probe `jsonschema`, `GET /health` reports
`skills.schemaValidation`. Tests: `test_memory_api_auth.py`,
`test_suggestion_api_scope.py`, `test_skill_contracts.py`; docs updated.

## ADR-H46 — Skill version identity covers instruction content, dependencies and drift

**Decision.** A version's persisted identity is
`SkillManifest.version_identity(instructions)` — the manifest PLUS a digest of
the `SKILL.md` procedure content — so an enabled skill's behavior cannot change
under the same recorded identity. At boot, if a stored version's identity and
its current manifest/instruction content disagree (a file edited without a
version bump), the registry records a `skill.version_drift` event and surfaces
it as a load error rather than silently serving changed behavior.

**Why.** `content_hash()` covered only the machine-readable manifest; editing a
`SKILL.md` in place changed behavior with no new identity and no signal.

**Impact.** `manifest.version_identity`, `registry.load_all` drift detection,
execution records carry the instruction-aware identity. Legacy manifest-only
hashes are still accepted (their stored `instructions` column preserves the
behavior identity), so existing databases do not report false drift.

## ADR-H47 — Memory retrieval is measured, gated on lexical relevance, and cross-user isolated

**Decision.** Memory retrieval has a versioned, human-labeled evaluation set
(`eclipse_memory/eval/dataset_v1.json`) and a runner reporting recall, precision,
scope leakage, forbidden hits, no-match cleanliness and context-budget behavior;
the recorded baseline is recall 1.0 / precision 0.5 / leakage 0 / forbidden 0.
Behind the existing seam, retrieval applies a deterministic **relevance gate**:
for a query with real terms, a topical memory with no keyword/subject signal is
not recalled merely because its importance/confidence is high; standing user
rules (`preference`/`constraint`) remain per-turn personalization exempt from the
gate. Scope/status/privacy filtering stays authoritative and deterministic — no
semantic similarity authorizes or broadens access. Cross-user isolation is
enforced on read (`actor_scope="user"` with no `scope_id` no longer leaks every
user's rows) and on suggestion accept/dismiss (a suggestion owned by another
scope is refused).

**Why.** Off-domain and near-match queries dragged in unrelated memories; and a
user-scoped retrieve without a `scope_id` leaked other users' memories.

**Impact.** `retrieval._score` returns a relevance signal; `find_suggestion_by_signature`
is scope-aware; `accept_suggestion`/`dismiss_suggestion` take `user_id`;
new tests `test_memory_retrieval_eval.py` and isolation cases.

## ADR-H50 — Retention is automatic and observable; contradictions are authority-resolved

**Decision.** Two memory areas were hardened without changing the architecture:

1. **Retention.** An automatically learned memory may receive an `expiresAt` from
   `retention_days`; explicit memory never does. The sweep runs automatically at
   runtime startup through the existing FastAPI lifespan (`_lifespan` →
   `run_startup_maintenance` → `run_retention_maintenance`) — no new daemon or
   thread, and a failure is a recorded diagnostic that never blocks boot. Each
   run is persisted in `MemoryMaintenance` (migration 11) and reported as
   inspected/expired/skipped/ranAt/error. Confirmation and renewal refresh the
   lifecycle timestamps and extend or clear an automatic memory's expiry. A
   policy change never mutates existing rows; retrieval excludes a due memory by
   timestamp independent of the sweep; expired memory stays auditable.
2. **Contradictions.** Conflict resolution is authority-driven: explicit
   replacement and explicit-over-automatic supersede (old→new linked, retained);
   automatic-vs-explicit and two ambiguous explicit statements store the new
   record inert (`proposed`). Detection is deterministic and conservative —
   subject identity via equality or `SUBJECT_ALIASES`, normalized (synonym/
   stemmed) tokens, known opposing pairs, and explicit replacement wording; a
   missed conflict is preferred over replacing unrelated memory.

**Why.** `expire_due_memories()` existed but nothing ran it, and
`_resolve_conflict` accepted an `authority` argument it never used — so retention
was manual-only and an explicit statement could not override a learned one
without magic wording. Both are table stakes for a trustworthy personal memory.

**Impact.** Migration 11; `service.{run_retention_maintenance,retention_status,
renewal_expiry}`, `store.{record_maintenance,maintenance_status}`,
`conflicts.detect_conflict` (authority-aware) + `same_dimension`;
`main._lifespan` startup hook + `/eclipse-memory/retention`; an honest
`needs_review` memory-action outcome; Control Room retention/conflict views.

## ADR-H49 — Memory is a local personal system: explicit lifecycle, deterministic contracts, operator control

**Decision.** Eclipse-Memory stays a single-user, local system (`userId`/`scopeId`
are labels, not security identities) and is matured without rewriting its
architecture:

1. **Explicit lifecycle.** Every `MemoryRecord` carries `createdAt`,
   `lastConfirmedAt`, `lastUsedAt`, `lastReviewedAt`, `expiresAt`, `status`,
   `statusReason`, `supersededBy`, provenance and confidence, plus an
   `authority` (`explicit` vs `automatic`). Re-stating a fact refreshes
   confirmation rather than duplicating. `expired`/`superseded`/`rejected`/
   `archived` are never injected. Retention only ever expires **automatic**
   memories; explicit memories are never silently expired. History is never
   hard-deleted by default.
2. **Deterministic contradiction handling.** `conflicts.py` detects a same-scope
   conflict lexically. Explicit replacement supersedes the old record (linked,
   retained); an ambiguous contradiction is stored inert (`proposed`) for review
   — two contradictory preferences never coexist as active truth. Scope isolation
   is authoritative (different scopes never conflict).
3. **Measured retrieval, no premature semantics.** Retrieval normalization
   (synonyms, light stemming, subject aliases, bounded typo tolerance) is added
   behind the existing seam and judged by the labeled set with release
   thresholds. Semantic/embedding retrieval is **deferred**: the eval shows no
   measured need, so no dependency or network service is added. Scope/status/
   privacy filtering remains authoritative; similarity could only ever find
   candidates, never authorize access.
4. **Operator control.** Export/import/backup/health/reset are local operator
   actions (`transfer.py`); import runs through the same decision gate and write
   pipeline with `imported` provenance; reset requires explicit confirmation,
   backs up first, and clears only the memory domain. Policy gains a hard
   `memory_enabled` off switch and per-category capture/recall rules that can only
   tighten.
5. **Measured skill quality.** Skill usefulness (success/validation/tool-budget
   metrics, version regression, deprecation advisory) is derived from real
   executions; promotion remains evaluation + operator gated and is never
   automatic.

**Why.** The system must be correct, private, recoverable, explainable and
honest about its limits — the properties a personal memory system needs and a
hosted multi-tenant design would obscure.

**Impact.** Migration 10; new modules `conflicts.py`, `normalize.py`,
`transfer.py`, `skill_quality.py`; policy keys `memory_enabled`,
`memory_in_diagnostics`, `semantic_indexing_enabled`, `capture_policy`,
`recall_policy`; lifecycle/export/import/backup/reset APIs + Control Room
Lifecycle tab; release thresholds in the eval. Verified by the memory,
lifecycle, conflict, normalization, transfer, privacy, reliability and
skill-quality test modules.

## ADR-H43 — MCP is presented as finance workflows with provenance, diagnostics and safe defaults

**Decision.** A product layer sits on top of the MCP machinery:

1. **Finance presets & workflows** (`python/harness/mcp/presets.py`). Known
   finance integrations (Sheets, Excel, filings, web search, calendar, cloud
   docs, Canva/Figma/Office decks, Notion) with plain-language setup, plus named
   workflows a user recognises — Import Portfolio, Review Portfolio Risk,
   Prepare Earnings Brief, Compare Companies, Analyze Trade Journal, Create
   Investment Memo, Export Portfolio Report. Each workflow lists its steps, which
   integration each step uses, which steps are native (Eclipse data), and which
   need approval. Presets are **data**, contain no secrets, and never activate
   anything — a workflow is a plan the user reviews.
2. **Honest labeling.** Every integration says whether its launch values were
   `verified` against the package registry; unverified entries are marked
   `UNVERIFIED` in their notes and remote templates are flagged. Community
   servers are labelled.
3. **Source provenance on every result.** Each MCP result carries a machine-
   readable `provenance` block (`verification: "external"`, `eclipseVerified:
   false`, `source`, `retrievedAt`, `truncated`) and the result text says
   "EXTERNAL source … NOT Eclipse-verified". Eclipse's native JDdS/portfolio data
   remains authoritative; a workflow's native steps are marked `native_data`.
4. **Setup diagnostics** (`python/harness/mcp/diagnostics.py`): command / Node /
   npx / Python availability, vault secret references, endpoint safety +
   reachability, connection state, discovery and selection — each with a
   `recovery` step. A whole-environment check also reports whether a writable
   temp directory exists (Windows permission problems must not look like a broken
   server).
5. **Approval clarity.** An effectful approval records a plain-language
   `actionSummary`, the `affectedData`, and a `risk` level alongside the argument
   digest; the UI shows them and uses "Approve this exact call".
6. **Resilient tests.** `python/harness/mcp/_testtmp.py` resolves a writable temp
   base, falling back from `%TEMP%` to a repo-local `.tmp-tests`, so a locked-down
   Windows temp dir cannot make a healthy test look broken.

**Why.** A user should not have to reason about servers, JSON and tool names to
do a finance job, and must never mistake external data for Eclipse-verified
data. The runtime already enforced execution safety; what was missing was
task-orientation, provenance, and actionable setup feedback.

**Consequences.** The wizard/API expose integrations and workflows read-only;
activation still requires an explicit operator action and read tools still need
selection + catalog confirmation, writes still need per-call approval. Secrets
remain vault-only. Automated end-to-end coverage
(`python/tests/test_mcp_workflow.py`) proves import → native analysis → report →
approved export → provenance, and that a changed payload needs a new approval.

## ADR-H51 — Memory expansion: profile, session recall, learning review, file projection (all projection, no second store)

**Decision.** Five capabilities were added to Eclipse-Memory without changing
its architecture (one `eclipse-memory.db`, one `EclipseMemoryService`, one
decision gate, one retrieval seam; `agent-memory.db` stays the run store):

1. **Compact prompt profile** (`eclipse_memory/profile.py`) — a deterministic,
   bounded *materialized projection over active memories*, built once at run
   start into a labelled, non-authoritative `SystemMessage`. Hard limits
   (user/project/total chars, entries, per-entry chars) are code constants; the
   policy may only tighten. Excluded statuses/sensitive/financial/other-user/
   mismatched-task content is excluded WITH a reason. Memory text is sanitized
   and fenced as DATA. Only reproducibility metadata is persisted
   (`MemoryProfileSnapshot`, migration 12) — never a second copy of the memory.
2. **Full-session historical recall** — a normalized, redacted, bounded
   `SessionMessage` search index (+ FTS5 mirror) in `agent-memory.db`, reached
   through read-only `session_search`/`session_open` tools. History is context,
   never current evidence; the prompt says so explicitly. FTS5 absence is
   reported honestly (LIKE fallback), never faked.
3. **Automatic learning review** (`harness/learning_review.py`) — a bounded
   in-process asyncio queue that reviews completed runs after the response. The
   deterministic path reuses `analyze_run`; an optional model review may propose,
   but its output is inert and re-authorized by the shared gate. No skill is ever
   activated; no durable write bypasses `authorize_proposal`; no secrets, market
   facts, predictions or one-off details are captured; a single market/provider
   failure is never generalized globally.
4. **File projection** (`.black-eclipse/memory/{USER,MEMORY,PROFILE,README}.md`)
   — an inspectable Markdown *view* with explicit export/import/backup/restore.
   Imports reuse the existing gated `import_payload` pipeline; SQLite stays the
   source of truth; there is no filesystem watching.
5. **External-memory posture unchanged** — MCP/provider data remains external and
   never Eclipse-verified; native memory remains separate from JDdS.

**Why.** These are real product gaps (a run had no stable personalization
snapshot, no way to ask "what did we decide last week?", and no safe automatic
self-review). The brief required them WITHOUT replacing SQLite with Markdown,
adding a third-party memory platform, or letting background learning activate
skills. Modelling each as a *projection* / *bounded queue* over the existing
structured store satisfies the capability while preserving the ONE gate and the
safety floor.

**Consequences.** New policy keys (`profile_*`, `session_*`) are validated and
bounded. `graph.execute_run` now injects a persistent-context block and emits
`session.indexed` on completion. The runtime gains a learning-review queue
started/stopped by the FastAPI lifespan. `MemoryProfileSnapshot` (migration 12)
is additive; `SessionMessage`/`SessionMessageFts`/`LearningReview` are new tables
in `agent-memory.db`. No new dependency, no embeddings, no cloud service.

## ADR-H52 — External memory providers are a separate, fenced layer over the MCP boundary

**Decision.** External memory is exposed through a dedicated
`python/harness/memory_providers/` layer that implements one `MemoryProvider`
contract. The native provider wraps the existing `EclipseMemoryService`; the MCP
provider reuses the existing `MCPManager` connections and approval gate. Every
result carries `provider`/`provenance`/`verified`/`retrievedAt`; an external
result defaults to `provenance=external_provider`, `verified=false`, is fenced as
`[EXTERNAL MEMORY — PROVIDER: <name> — UNVERIFIED CONTEXT]`, and is NEVER
promoted to native memory. Routing is native-first, external search requires both
a policy enablement AND an explicit per-call allow, and external writes require
an explicit user request AND an operator approval. There is no generic "memory
table": the four layers (native truth, versioned skills, external providers,
session archive) stay distinct.

**Why.** The gap was not MCP tool access (already mature) but a first-class,
provenance-labelled memory-provider contract that cannot silently overwrite
native memory or masquerade as Eclipse-verified. Reusing the MCP boundary avoids
a second client, a second secret path, or a second approval flow.

**Consequences.** New policy keys `external_memory_search_enabled` (default off),
`external_memory_write_enabled` (default off) and
`external_memory_native_sufficiency`. Automatic external writes are structurally
absent (the provider never declares `write` for automatic use). Three read-only
tools and `/memory-providers/*` routes were added. ADR-H40's vault limitation is
inherited unchanged.

## ADR-H53 — Self-improving skills are structured patches that become new versions; activation is evaluated, canary is bounded, rollback is atomic

**Decision.** A skill change is a structured JSON-pointer patch (`replace`/`add`/
`remove`) validated against an explicit allowed-field set (`description`, `tags`,
`name`, `instructions`, `outputSchema`, `limits`). Identity, permission, tool,
risk and lifecycle fields are not patchable. A patch creates a NEW `SkillVersion`
(the active version is never mutated) and is rejected when its `baseVersion` is
stale. Activation requires a passing evaluation; canary is limited to safe,
non-mutating, low-risk skills and is never allowed for security/permission/
external-write/policy-shaping skills. Rollback (manual or automatic on a
regression/failure/correction signal) is atomic and preserves both versions.

**Why.** The product goal is autonomous discovery and proposal, never autonomous
silent change of truth, permissions or safety behavior. Making every change a
reviewable, versioned, diffable patch — with evaluation before activation and an
automatic rollback — gives the autonomy while keeping it reversible and governed.

**Consequences.** Migration 13 adds the patch/version metadata columns to
`SkillVersion`; new lifecycle statuses `evaluating/canary/approved/active/
superseded/rolled_back`; `registry.load_all` treats the store's `latestVersion`
as authoritative so a reload never walks a patched skill back to its source
manifest. A background review may record a `skill_patch` opportunity but never
creates a version.

## ADR-H54 — Hybrid memory ranking uses logical namespaces and a bounded semantic term; similarity never authorizes

**Decision.** `eclipse_memory/hybrid.py` maps memories to logical namespaces
(preference/project_fact/correction/workflow/skill/session_summary) and combines a
bounded BM25 term, the existing lexical signal, authority/scope/recency/access
signals and an OPTIONAL, bounded semantic term. The semantic term can only nudge
an already-authorized, already-lexically-relevant memory; it can never surface an
excluded memory, confirm, supersede, archive or authorize. There is deliberately
no persistent vector index and no hosted embedding service (consistent with
ADR-H49 and the no-new-infrastructure rule).

**Why.** Semantic similarity is retrieval assistance, not authority. Modelling it
as one bounded component of a deterministic hybrid score — with content
categories kept in separate ranking namespaces — captures the useful part while
making "unauthorized supersessions = 0" structurally true.

**Consequences.** The labeled semantic eval gained typo, profile-mismatch and
temporal-replacement cases; the release gate's absolute safety floors are
unchanged.

## ADR-H55 — Prompt caching is explicit: immutable segments and a stable identity-only cache key

**Decision.** `python/harness/prompt_segments.py` splits the prompt into named
segments (system policy, agent identity, tool schemas, profile snapshot, session
summary, skill manifest, run instructions, user message), each with a content
hash, source, version and token estimate. A `prompt_cache_key` is composed only
from identity (agent/policy/tool-schema versions + profile snapshot id + skill
manifest version + session-summary version), so a new user turn or new run
instructions do not invalidate the reusable segments, and a profile or skill
change invalidates only that segment. Skills are injected as a bounded,
relevant-only manifest (never all skills); full instructions stay behind
`skill_view`.

**Why.** Hermes-style caching is only useful when the reusable prefix is stable
and observable. Making segments explicit and the key identity-only gives stable
reuse and precise invalidation without changing what the model may do.

**Consequences.** `graph.execute_run` emits a `prompt.plan` event with the segment
hashes and per-segment token estimates. No behavior/permission change.

## ADR-H56 — Long-lived sessions belong to a profile; session recall is ranked and bounded

**Decision.** A durable `ChatSession` (metadata + a bounded deterministic summary)
lives in `agent-memory.db`; a run belongs to a session, a session belongs to one
profile. Session search ranks with the documented hybrid (exact phrase > BM25 >
decision/correction/skill-failure/memory-action > recency > prose) and filters by
role/kind/session/profile/market/skill/memory-action. A session summary is
searchable and opt-in but is NEVER injected into every prompt. Historical content
is context, never current evidence (the prompt says so).

**Why.** The prior `SessionMessage` was a run-keyed search index with BM25 only,
no session identity, no lifecycle and no summary. Users need "continue this
session" and "what did we decide last week?" without an unlimited transcript ever
entering the prompt.

**Consequences.** `ChatSession` + scope columns on `HarnessRun`/`SessionMessage`
are additive. New `/sessions*` and `/profiles*` routes; `RunRequest` carries
`sessionId/profileId/projectId`. Delete archives by default and, when hard, clears
only the search index — the run trace is never destroyed.

## ADR-H57 — Named profiles are a metadata registry with a read-only inheritance chain

**Decision.** `eclipse_memory/profiles.py` is a metadata registry over
`.black-eclipse/profiles/PROFILES.json` plus a directory projection
(`PROFILE.json`, `sessions/`, `skills/`, `history/`, `exports/`). A profile scopes
memory, sessions, skills and providers and carries its prompt profile, retention
and settings. Inheritance is explicit and READ-ONLY in the child; cycles and
deleting a parent with children are refused. SQLite remains canonical for
structured records — the directory is a projection.

**Why.** Profiles are stronger isolation than separate directories: every query
resolves the profile scope and a cross-profile read is refused. Keeping the
registry as metadata (not a second store) preserves the one-store architecture.

**Consequences.** `ProfileRegistry` is owned by `EclipseMemoryService`. Profile
ids are validated slugs; the `default` profile cannot be deleted. No provider
secret or memory content is written to the directory.

## ADR-H58 — File edits are atomic, versioned and reversible; the file is never the source of truth

**Decision.** The Markdown projection is edited only through a targeted API with
an `expectedVersion` stale-edit guard, atomic writes (temp + fsync + rename), a
pre-regenerate backup, and a structured revision history (before/after/actor/
sourceRun/reviewId/reason/affectedIds/parentRevision/timestamp) with rollback and
a bounded diff. A stale expected version is refused. Archive/restore remain
structured-memory actions, not file edits.

**Why.** A direct `writeFile` could lose a concurrent edit or leave a partial
file, and a hand edit had no audit trail or way back. The brief requires atomic,
diffable, reversible edits while SQLite stays canonical.

**Consequences.** Entry markers carry a `version`; files are `USER_PROFILE.md`,
`MEMORY.md`, `PROJECT_MEMORY.md`, `SKILLS.md` (+ `PROFILE.md`/`README.md`). Routes
`/files/edit` and `/files/history`. Import still routes every entry through the
existing gated pipeline.

## ADR-H59 — Project-local skills are inert until an operator trusts the root

**Decision.** A repository may carry skills under `.black-eclipse/skills/` or
`.agents/skills/`. `python/harness/skills/project_skills.py` discovers them, but
the registry loads a project's skills **only** after an explicit, revocable
operator trust decision persisted in `ProjectSkillTrust` (migration 14). An
untrusted root yields a names-only notice — its prose is never read. Trust is
per absolute path. Precedence is deterministic: **project > profile > bundled**;
a project skill may shadow a bundled skill of the same id (recorded as
`shadowed`, not a duplicate error).

**Why.** Skills are procedures the agent follows, so auto-loading them from any
cloned repo is a prompt-injection/privilege risk. Trust makes the decision
explicit and auditable while still letting project conventions travel with the
code. Reusing the existing registry/permission/execution path (rather than a
second skill system) keeps one source of truth and one default-deny gate.

**Consequences.** A project skill cannot grant itself a permission, enable
itself, or bypass evaluation — it runs through `runtime.execute_skill` with the
same permission check and immutable-version identity as any other skill.
Discovery can be disabled globally (`project_skill_discovery`). `untrust`
immediately stops injection on the next load. Routes `/skills/project`,
`/skills/project/trust`, `/skills/project/untrust`; UI Skills › Project Skills.

## ADR-H60 — Skill bundles are references, never a way to enable or widen

**Decision.** `python/harness/skills/bundles.py` groups existing skills under a
stable id with optional instruction/constraints, persisted in `SkillBundle`
(migration 15). `resolve_bundle` is deterministic and reports `missing` and
`unavailable` members honestly. `RunRequest.bundleId` expands a bundle into the
bounded skill manifest instead of keyword discovery, emitting
`skill.bundle_resolved`. Members pass the same permission check when an actor is
supplied.

**Why.** A bundle is composability for recurring workflows; it must not become a
back door. Treating it as a reference (not a copy) means a disabled skill stays
disabled, a missing skill is reported, and the permission gate is untouched.

**Consequences.** A bundle cannot enable a skill, grant a permission, or exceed
the prompt budget (members are capped at 12, content at 1200 chars). Bundle ids
are validated slugs; content is bounded on write as well as on read. Routes
`/skill-bundles` (+`/{id}`); UI Skills › Bundles.

## ADR-H61 — Guided learning authors an inert, sanitized draft from an explicit source

**Decision.** `python/harness/skills/learn.py` turns an explicit user request
(run / document / repository / repeated-workflow / correction) into a complete
but inert skill draft via the existing `propose_draft` path. Content is
sanitized (secrets, raw transcript lines and issue references are removed) and
advisory-linted (dates, first-person narration) before the draft is built. The
source is user-supplied and operator-gated; the draft stays
`status: draft`/`not_evaluated` and can only activate through the existing
evaluation + operator promotion controls.

**Why.** Hermes' `/learn` is a great shortcut for capturing a reusable
procedure, but an unguarded version would let raw logs, secrets or one-off
incidents become active procedures. Sanitization + inertness + operator gating
give the workflow without the risk.

**Consequences.** One-off runs never auto-create an active skill; recurrence
evidence stays on the candidate. A learning-origin manifest without a real run
uses a stable synthetic `learn:<kind>:<slug>` source reference. Route
`/learning/from-source`; UI Skills › Learn a Skill.

## ADR-H62 — The learning journey is a derived read model, not a second source of truth

**Decision.** `python/harness/learning_graph.py` projects a node/edge graph
(memories, skills, versions, candidates, corrections, mistakes, promotions,
sessions) from canonical rows on demand. It never writes, never stores a copy,
and is bounded (≤400 nodes / ≤800 edges). Secrets are never exposed (labels are
ids/type metadata), scope isolation filters the set, and inactive items appear
with a status rather than being deleted.

**Why.** Users need to understand *why* a skill or memory exists; Hermes'
Learning Journey shows the value. Deriving the graph keeps the canonical store
authoritative and avoids drift between a graph copy and reality.

**Consequences.** Edge relations are a fixed vocabulary (`created_from`,
`corrected_by`, `superseded_by`, `used_in`, `derived_from`, `promoted_from`,
`evaluated_by`, `related_to`). Route `GET /learning/journey`; UI Skills ›
Journey. Filters by kind/status/since; editing still goes through existing
persistence/authorization paths.

## ADR-H7 — Zero-config is preserved via automatic provisioning**Decision.** `postinstall` and `doctor.js` install the Python agent stack
automatically; the runtime is spawned on demand. If Python is genuinely
unavailable, runs fail with a clear 503.

**Why.** `npm install && npm run dev` must keep working for open-source users,
now that the agentic runtime is Python.

**Consequences.** First run may take longer while pip installs. `npm test` runs
both the Vitest and pytest suites; the Python suite is skipped (not failed) when
the stack is absent.

## ADR-H63 - Context windows are declared catalog data; an unknown window stays unknown

**Decision.** The context window is a `ProviderSpec.context_window` field plus a
`MODEL_CONTEXT_WINDOWS` model-substring table, resolved by a pure
`resolve_context_window(provider, model)`. Where a provider's models vary, the
declared value is a conservative FLOOR with a documented source; where the
runtime cannot know the window (local servers, routers, a custom endpoint) the
value stays `None`.

**Why.** The runtime previously bounded history with hardcoded constants and
never knew its model's window, so a small-context model overflowed and a
large-context model wasted most of its window. Declaring windows as data follows
the existing catalog pattern (add a provider = add an entry) instead of a branch
per vendor. Guessing a window would be worse than not knowing: it would make the
runtime over-confident on exactly the models it understands least.

**Consequences.** An unknown window makes the budget inert and falls back to the
old `MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS` ceiling; every surface reports
"unknown". Adding a window is a one-line data change with provenance. No network
call is ever made to discover a window.

## ADR-H64 - Overflow is classified, retried once against a tighter budget, then reported honestly

**Decision.** `CONTEXT_OVERFLOW` is a first-class `HarnessErrorCode`. A
conservative classifier in `models.py` recognises a provider's context-length
rejection (structured code OR a bounded, specific message pattern) before the
generic provider catch-all. On a first-call overflow — before any tool ran — the
run retries ONCE with half the derived history allowance; otherwise it fails
with a specific message and the remedy. Exactly one terminal status is persisted.

**Why.** A provider context-length rejection previously fell through to a generic
`PROVIDER_ERROR` with no recovery and no explanation. A single bounded retry is
the cheapest honest recovery; looping would risk duplicate side effects, and
retrying after a tool executed would re-run that tool.

**Consequences.** Overflow is distinguished from rate-limit / timeout / auth /
quota errors (false-positive guarded by tests). Recovery is first-call only and
is skipped when the tightened history would not actually be smaller. The success
path emits `memory.history_bounded` (counts/estimates only) so a trimmed turn is
never silent; the `RunResult.context` blob is additive and absent for old rows.
A token-aware summarization ladder remains explicitly out of scope, gated on this
event data.

## ADR-H65 - Memory recall is surfaced as a content-free activity line, not a run-result field

**Decision.** `memory.retrieved` (already emitted by `_memory_context` with a
bounded payload) is mapped in `src/lib/agent/events.ts` to one activity item with
a new distinct `kind: 'recall'` (icon `Brain`), mirroring the `history_bounded`
mapping: counts and character budget only, `selected <= 0` emits nothing, and
`selectedIds`/`excluded`/memory text never reach the UI. No run-result contract
field is added.

**Why.** Trimming was visible but recall was not — the last observability
asymmetry, even though the runtime already told the UI everything needed. A
run-result `recall` blob would have no reader; the activity passthrough is the
one mechanism that already renders this class of fact, so a second one would be
redundant. Keeping the line content-free preserves the same privacy posture as
the dropped-context seam.

**Consequences.** A recalled-memory turn shows one `recall` line beside the
`bounded`/`retrieval` lines; the expandable detail is the existing name-only
panel, so no new detail variant exists. Memory content remains out of the UI
(asserted by test). A future richer recall surface can read the same event data
without a contract change.

## ADR-H66 - An unknown context window is operator-declarable, and ModelSettings accepts the camelCase wire shape

**Decision.** `ModelSettings` gains an optional bounded `context_window`
(camelCase `contextWindow`, 1..10,000,000). The budget resolver prefers an
explicit override, then the declared value, then the catalog resolver; blank
stays unknown (conservative ceiling, `windowKnown: false`). Separately,
`ModelSettings` now generates camelCase aliases (`to_camel`) with
`populate_by_name=True`.

**Why.** The catalog cannot know a local server's, a router's or a custom
endpoint's window, so those runs were permanently stuck at the conservative
ceiling even when the operator knew the limit. A declaration is real input,
never a guess. The alias fix addresses a pre-existing bug: the TS front door
sends `baseUrl`/`apiKey` but the model declared `base_url`/`api_key`, so
pydantic silently dropped both and the runtime used the catalog default base
URL with no credential.

**Consequences.** Settings > AI / LLM shows the resolved window and offers a
numeric field only when it is unknown; an emptied field sends `null`, which
`setLLMConfig` treats as an explicit clear. Both wire shapes are accepted, so
existing TS callers and snake_case test constructors both work. `jdds.db`
untouched.

## ADR-H67 - MCP config is shareable, screened and trusted in tiers; tool names use a double-underscore boundary

**Decision.** Phase 6 Milestone 1 hardens the MCP config contract:

1. **Interpolation.** `${VAR}`/`${env:VAR}` and the built-ins `${workspaceFolder}`,
   `${userHome}`, `${pathSeparator}` are resolved from the process environment at
   load/spawn. One pure function (`mcp/interpolation.py`); remote `url`/`auth`
   values **refuse the connect by name** on an unresolved reference; local stdio
   `command`/`args`/`env` keep the literal placeholder when unset.
2. **Filters.** `selected_tools` accepts the legacy exact list (unchanged) or
   `{include, exclude}` with fnmatch globs; include wins over exclude; an empty
   include selects nothing.
3. **Screening.** A static screen (`mcp/screening.py`) refuses — never sanitizes —
   a shell interpreter with an inline flag, shell control operators, a download/
   execute or exfil shape, and a known-IOC package token; it runs at load, at
   save, and at spawn so a hand-edited file cannot bypass it.
4. **Trust tier.** `trust: "full" | "untrusted"`, fail-closed on an unrecognized
   value. Untrusted requires a per-call approval for every non-read call
   regardless of `enabled_effects`, and its annotations can never activate a
   tool.
5. **Naming.** Eclipse tool names are `mcp__<server>__<tool>` (double underscore),
   disambiguating the server/tool boundary; the identity digest survives only as
   a genuine-collision last resort.
6. **Read routes.** The Python MCP read routes are operator-gated at the boundary.
7. **`httpx2`** is pinned explicitly (it is a declared transitive dep of `mcp`).

**Why.** A config a user cannot share, a filter that makes selection unusable, a
hostile entry that executes, a secret in plaintext and an undocumented
authorization story are exactly what users get wrong. Trust must be a declared
tier, not inferred from a server's own metadata; a changed delimiter must be
provably safe for saved configs (activation keys on original names).

**Consequences.** Interpolation is applied in memory and never written back, so
the file stays shareable. Screening is defense-in-depth on top of argv-only spawn
with no shell. `selected_tools` remains compatible, and existing configs activate
the same tools across the delimiter change (tests). The IOC list is a documented
seed, not a completeness claim. `jdds.db` untouched.

## ADR-H68 - MCP lifecycle is resilient: separate retry budgets, honest session-expiry, and platform-appropriate orphan reaping

**Decision.** Phase 6 M2 makes the MCP layer survive transient failures:

1. **Retry/reconnect budgets.** `mcp/lifecycle.py` `RetryBudget` keeps separate
   initial-connect and reconnect-after-drop counters with full-jitter exponential
   backoff and an explicit terminal state that is reported with the attempt count.
   Startup never crashes the service; cancellation propagates.
2. **Call-time reconnect seam.** A call at a `failed`/`closed`/`lazy` server
   triggers ONE bounded reconnect under a per-server lock; after reconnecting the
   live descriptor is re-fetched and selection/digest/effect are re-checked, and
   only tools passing the same authority checks are re-registered.
3. **Session-expiry policy.** A mid-call transport/session error is classified.
   A **read** is reconnected and replayed exactly once; a **write/external_action**
   is NEVER replayed and returns an explicit `outcomeUncertain` outcome.
4. **Keepalive/recycle.** One manager lifecycle task (started/stopped with the
   manager — not a daemon) pings a live session on `keepalive_interval` and
   recycles a stdio child on `idle_timeout_seconds`/`max_lifetime_seconds` only
   when no call is in flight.
5. **Orphan reaping.** `mcp/orphan_supervisor.py` (stdlib-only) starts ONE
   supervisor per process on POSIX; it detects parent death by pipe EOF and sweeps
   registered process groups TERM?grace?KILL. Clean shutdown unregisters. On
   Windows the MCP SDK spawns each child in a Job Object with
   `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, which already kills the tree when the
   parent dies, so no supervisor is started.
6. **Lazy startup.** `mcp/schema_cache.py` persists a per-server tool manifest
   keyed by a fingerprint of the connection-defining config; a `lazy` server
   registers from cache and spawns on first call. `lazy` defaults off.

**Why.** One transient blip permanently disabled a server until a manual reload; a
suspended HTTP session made the first call after a pause fail as a generic error;
a crashed parent leaked `npx` children; and boot spawned everything eagerly. The
honest session rule is a correctness requirement: a write that may have happened
must say so, never silently replay or silently fail.

**Consequences.** The orphan guarantee on Windows is the SDK's Job Object, not our
code (verified by a real-kill test). POSIX reaping registers a child's process
group by polling `ps` briefly after spawn; where that is unavailable it is a
no-op and the SDK's own teardown remains the only guarantee. The lifecycle task is
one per manager, so nothing outlives the runtime. `jdds.db` untouched.

## ADR-H69 - Remote MCP uses the SDK OAuth client; its tokens live encrypted in the vault, keyed by server id

**Decision.** Phase 6 M3 adds OAuth 2.1 to remote MCP servers. The
authorization-code + PKCE path reuses the MCP SDK's own `OAuthClientProvider`
(no new dependency); a device-code (RFC 8628) flow the SDK lacks is implemented
in `mcp/oauth.py`. Tokens, client registration and issuer metadata are stored
ENCRYPTED at rest in JDDS (`SystemConfig.key = 'mcp_oauth_tokens_v1'`,
AES-256-GCM), referenced by server id, never in `mcp-servers.json`, an event, a
log, or a response. If the vault cannot encrypt, saving throws — no plaintext
fallback. Clear-credentials stays configured-but-disconnected. `ssl_verify`
(true|false|CA path), mTLS (`client_cert`/`client_key`), SSE transport and a
redirect/origin re-validation hook are added on the same lifecycle.

**Why.** Every hosted finance server an investor would connect uses OAuth; without
it they are unreachable. A token is a credential: it must be encrypted, never
serialized, and never persisted in the gitignored plaintext config.

**Consequences.** The interactive authorization-code path is wired but not
exercised end-to-end in the offline suite (device flow is). `jdds.db` untouched.

## ADR-H70 - MCP resources and prompts are capability-aware utility tools; subscriptions are a non-goal

**Decision.** Resources/prompts utility tools register only when the live session
advertises the capability AND the operator toggles `tools.resources`/`tools.prompts`
(default off). A resource read is bounded, labelled and scheme-authorized;
prompt text is returned as INERT data. **Subscriptions are not implemented.**
Shipping them well needs ownership, rate limiting, a bounded queue, a drop-oldest
policy with an honest drop count, and a decision that a notification triggers
nothing — none of which exist, and inventing a second event bus is forbidden, so
the honest choice is a documented non-goal. A notification can never trigger a run
or a write.

**Why.** An MCP server that is primarily a document source looked empty without
resources/prompts; but a notification channel is a real new authority surface and
must not be improvised.

## ADR-H71 - Sampling is off by default and capped; elicitation routes through the existing approval surface

**Decision.** `sampling/createMessage` is off per server; when enabled it has a
hard max-tokens cap, an RPM cap, a max tool-round count (0 = no tool use), a
timeout, audit counters, and a harness event. It can never trigger an effectful
tool without that tool's normal approval and never widens the agent allowlist.
`elicitation/create` form requests route through the SAME approval authorizer (no
parallel prompt path); URL-mode requests are declined; consent is per-call, never
remembered. Sampling/elicitation content is untrusted data.

**Why.** These are the two directions where a server asks Eclipse for something —
genuinely useful and genuinely new authority. They ship last, off by default, and
audited.

**Consequences.** The sampling `run_model` seam is not yet bound to the chat
model, so a live sampling request is refused honestly (`mcp_sampling_unavailable`)
rather than served by a second adapter.

## ADR-H72 - MCP is a first-class retrieval candidate; conflicts are preserved; Eclipse-as-server stays narrow

**Decision.** Phase 6 adds `mcp/mcp_retrieval.py`: a `SourceCandidate` with
provider-independent provenance, three distinct freshness states
(`fresh`/`stale`/`missing`) plus `failed`, a `plan_candidates` that prefers the
fresher eligible source and **preserves conflicts** rather than silently choosing,
and a `RetrievalSource` adapter for a declared MCP tool. A generic MCP tool stays
directly callable and is never withheld for not implementing the contract. Presets
point at real endpoints with `verified_at`/`verified_against` and a one-click
install that writes a DISABLED, nothing-selected entry; a read-only offline
supply-chain audit reports pinned/unpinned packages. Separately, Eclipse exposes a
narrow READ-ONLY MCP server (`server_exposure.py`) with its own bearer auth
(distinct from the operator secret), no write capability, bounded pagination and
schema hygiene.

**Why.** MCP stops being a bolt-on when native planning can consider and explain an
MCP source; and an investor's other agents querying Eclipse's receipts is a moat
if — and only if — it cannot leak a credential.

**Consequences.** The new conflict/freshness planner is self-contained and tested
directly but is **not yet invoked by `retrieval/planner.py`** — the documented
seam gap. `jdds.db` untouched.

## ADR-H73 - MCP data sources flow into the native planner; sampling runs on the run model; the AC OAuth leg is a manual https step

**Decision.** The three Phase-6 seams left open at first close-out are closed:

1. **MCP ? native planning.** An operator-declared MCP data tool (a server's
   `data_source_tools: {tool: dataType}`) becomes a `RetrievalSource` via
   `manager.mcp_sources()`, is threaded through `ToolContext.mcp_manager` into
   `FinancialRetrievalLayer(mcp_sources=...)`, and is considered by
   `plan_retrieval(..., additional_sources=...)` AFTER native structured sources
   but BEFORE generic web. Provenance stays `secondary` / `eclipseVerified=false`;
   JDdS is never silently upgraded. An undeclared MCP tool stays directly callable
   and is never forced through the contract.
2. **Sampling on the run model.** `AgenticService._sampling_model_factory` binds
   server `sampling/createMessage` to the runtime's OWN `models.build_chat_model`
   with the run's credentials and the policy's token cap — never a second model
   adapter. Sampling is still off by default per server; with no run model bound a
   request is refused with `mcp_sampling_unavailable` (honest, never a fake model).
3. **Eclipse-as-server second client.** The offline suite now drives the exposure
   surface with TWO MCP clients: Streamable HTTP and SSE. The real Hermes interop
   remains the documented manual step.
4. **OAuth authorization code.** The SDK's `OAuthClientProvider` refuses to build
   its OAuth URLs over plain http (RFC 8252 https requirement), so the interactive
   browser leg is a documented manual https step; the construction seam
   (bridge-backed `TokenStorage` + caller redirect/callback handlers + the
   discovery/registration/token endpoints the SDK consumes) is tested. Device code
   is covered end-to-end offline.

**Why.** The remaining limitations were real seams, not cosmetic: without (1) an
MCP source could never be selected or compared by native planning; without (2) a
server's sampling request could never be served; without (3) "two clients"
interoperability was asserted from one.

**Consequences.** `plan_retrieval`'s new `additional_sources` argument is additive
and defaults empty, so existing callers/tests are unaffected. A declared MCP
source cannot displace a strong native structured provider (it is inserted only
before web). `jdds.db` untouched.

## ADR-H74 - MCP config round-trip: absent means preserve (Phase 6.1)

**Decision.** `upsert_mcp_config` implements a merge contract from the incoming
model's `model_fields_set`, not from `if value is not None`:

> Absent means preserve; explicitly present means replace - including an explicit
> `null` / `false` / `{}` / `[]` for clearing.

A caller that omits a field (an older UI, an API client, a script) cannot reset
it. The UI can still clear a field because `draftToInput` always sends every
field it owns. This makes one edit-and-save provably unable to widen a server's
authority by omission: `trust` cannot move `untrusted` -> `full`,
`enabled_effects` cannot gain a class, `tool_effects`/`data_source_tools` cannot
be dropped, `confirmed_catalog_digest` cannot be cleared, and `selected_tools`
cannot grow, unless the caller explicitly sends the change. `env` keeps its
documented write-only merge and `env_keys` behavior. `install_mcp_integration` is
create-if-absent, so re-installing a preset never resets an operator's changes.
`public_dict()` also emits the raw operator-set bounds so a view -> model -> view
round trip is lossless; `public_configs()` exposes the capability-toggles map as
`capabilityToggles` (the `tools` key holds the discovered array).

**Why.** The Phase-6 field set existed only on the wire, not in the UI payload.
Re-saving a server through Settings silently downgraded `untrusted` -> `full`,
disabled resources/prompts, dropped the data-source declaration and every tool
effect, and invalidated the catalog confirmation - a silent authority widening.

**Consequences.** A TS pure module `src/lib/harness/mcp-draft.ts` owns the
view<->draft<->input mapping and is round-trip tested
(`mcp-draft.test.ts`); Python tests `test_mcp_config_roundtrip.py` assert the
preserve/clear matrix, the authority-widening invariants, an idempotent re-save
and install/confirm preservation. `_ServerRuntime`, status/introspection and the
OAuth flow are pure-extracted from `manager.py` into `runtime.py`,
`introspection.py` and `oauth_flow.py`; `MCPManager` remains the facade with an
unchanged public API. `resource_schemes` adds an optional per-server URI-scheme
narrowing with the global allowlist as a hard ceiling. Non-text MCP content
reports MIME type + byte size rather than an opaque omission.

## ADR-H75 - The release gate is local and runnable, not a fictional CI workflow

**Decision.** The unreachable workflows at `Black-Eclipse-site/.github/workflows/`
are deleted. GitHub Actions reads only `/.github/workflows` at the repository root,
and this repo's git root is above the app directory, so those workflows never ran.
Rather than move them to the root (unverifiable without a push, and the sibling
`backup.yml` would cron a daily `sqlite3 jdds.db` against a file that is no longer
tracked), the gate becomes ONE local command:
`npm run check:all` -> `scripts/check-all.js`, which runs prisma generate,
typecheck, lint, `npm test` (vitest + Python) and `npm run test:evals` in order and
exits non-zero on the first failure. The three surviving eval gates (retrieval,
contradiction, compaction) are folded into `npm test` via `scripts/test-evals.js`
(offline, ~0.7 s), using the explicit-`sys.path` launcher the vendored interpreter
requires. The `semantic_cli` reference is gone: the semantic layer was deleted
deliberately and its removal is documented evidence.

**Why.** The stated release gate was fictional three ways: a CI job that could not
pass (a missing module), a workflow GitHub never reads, and eval floors no local
command ran. A gate that cannot run is worse than no gate: it implies coverage that
does not exist.

**Consequences.** CI on GitHub is now **absent by decision**, not by accident; a
future root-level `.github/` would be a deliberate re-introduction (and must add a
working Python install plus a `jdds.db` story first). The CHANGELOG obligation is
enforced by `.githooks/commit-msg` (non-doc change must stage the CHANGELOG; doc-only
exempt; `SKIP_CHANGELOG_CHECK=1` bypass mirrors the identity guard). The smoke test
remains operator-triggered and offline-excluded.
