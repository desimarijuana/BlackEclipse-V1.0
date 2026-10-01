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
   Windows temp dir cannot make a healthy test look broken. **(Moved 2026-09-30 to
   `python/tests/_tmp_helper.py` and adopted by `python/conftest.py` as the
   `tmp_workspace` fixture — see ADR-H80; it is test-only and no longer ships in the
   package.)**

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

## ADR-H76 - CI is restored at the repository root (amends ADR-H75)

**Decision.** A workflow is restored at the TRUE root path,
`.github/workflows/ci.yml` (GitHub Actions reads only `/.github/workflows` at the
repository root, which is why the old `Black-Eclipse-site/.github/workflows/`
never ran). It mirrors `Black-Eclipse-site/scripts/check-all.js` step-for-step:
checkout → Node 20 + Python 3.12 with the same caching → `pip install -r
python/requirements.txt` → `npm ci --ignore-scripts` → `npx prisma generate` →
`npx tsc --noEmit` → `npx eslint .` → `npm test` → `npm run test:evals`, with
`defaults.run.working-directory: Black-Eclipse-site`. The former `backup.yml` is
**not** restored: `jdds.db` is untracked runtime state now, so a checkout has no
such file and a daily `sqlite3 jdds.db` cron would always fail. A local DB backup
belongs in `scripts/`, not CI.

**Why this supersedes ADR-H75's choice (b).** ADR-H75 chose local-only because two
blockers made a root workflow unverifiable/unsafe: (1) `jdds.db` was being
untracked, so `backup.yml` would cron a missing file; and (2) there was no local
gate to mirror, so CI and local would have diverged. **Both blockers are gone:**
`jdds.db` is untracked and ignored (no CI job references it), and
`scripts/check-all.js` is a real, green local gate the workflow mirrors exactly.
The value of a running remote gate now outweighs keeping it local-only.

**Consequences.** The workflow's steps were validated locally in the same order
(all exit 0); a root-level workflow is **unverified against GitHub until it is
pushed** — the user must observe the first run. `ADR-H75`'s local gate remains the
source of truth and is unchanged; CI is its mirror. `test:smoke` stays
operator-only (network) with a documented trigger in `CONTRIBUTING.md` (run before
a release tag).

## ADR-H77 - A provider-side error body is a failure, never retrieved data

**Decision.** An MCP call that reports transport success (`isError=false`) but
whose whole text body parses as a JSON object carrying an unambiguous error signal
(a truthy `error` key, a 4xx/5xx `status`/`statusCode`, or a known error `code`
with a status or message) is classified as a **provider error**. The pure rule
lives in `client.looks_like_provider_error` and is deliberately conservative — a
legitimate payload that merely carries a `code` is not misread. On a match,
`_normalize_result` sets `is_error=True` and records `data["providerError"] =
{code?, status?}` with the provider's body preserved verbatim; the manager renders
an explicit `MCP reported a provider error (status …, code '…'): <body>` failure
and emits `mcp.tool.failed` with `mcp_tool_provider_error` (never
`mcp.tool.completed`). A provider error is NEVER retried — it is not a transport
error. The MCP system prompt instructs the model to report such a result as a
limitation and never present it as retrieved data.

**Why.** Connecting real servers exposed the defect: `@notionhq/notion-mcp-server`
with an invalid token returned `ok=True, isError=False` and the body
`{"status":401,"code":"unauthorized","message":"API token is invalid."}` — handed
to the model as a normal successful result. Reporting "connected" when all that is
known is that a child process launched is a lie of omission.

**Consequences.** An empty MCP result is labelled `(the server returned no text
content for this call)` so empty never reads as a successful empty result. The
rule catches a structured JSON error body; an error phrased as free prose is not
caught by the classifier and is covered by the prompt rule instead.

## ADR-H78 - Test is not Verify; credentials are proven by an explicit read call

**Decision.** The operator-facing **Test** action only proves that a server's
process started and tools were discovered; its copy says so and it never calls a
tool. Credential validity is a SEPARATE, operator-triggered **Verify** action
(`POST /mcp/servers/{id}/verify` + `MCPManager.verify_credentials`, extracted as
`VerifyMixin`). Verify calls ONE operator-chosen **read** tool with
operator-supplied arguments, bounded by a short fixed timeout, and records a
content-free verdict — `credentials_valid` / `credentials_rejected` (with the
provider's status/code) / `verify_inconclusive` — plus `verifiedAt`. It never
returns or stores the response body, is never automatic, never at boot, never in a
loop, and refuses a non-read tool. A `credentials_rejected` server is presented
distinctly from `endpoint_unreachable` and `server_not_connected`: a server can be
connected AND rejected.

**Why.** "Test" reporting `connected` for a server that cannot complete a single
call was the defect that cost real time; the only symptom was a 401 buried inside
a result body. Separating "the process launched" from "the credential works" makes
both honest.

**Consequences.** A server with no declared read tool cannot be verified (the UI
says so). Verify can only prove what the chosen read tool proves.

## ADR-H79 - Effect classification refuses a write-shaped name on a read tool

**Decision.** Effect classes are never inferred from a tool name. Instead, a tool
marked `read` (declared or annotation-sourced) whose NAME contains a write-ish
token (`create|delete|update|patch|move|post|append|set|remove|write|archive`,
`naming.writes_like_name`) stays **inert** until the operator explicitly
acknowledges the mismatch
(`MCPServerConfig.acknowledged_effect_mismatches`, a per-tool list). The editor
shows the mismatch and requires the acknowledgement before the tool is
selectable. A server's own naming and its `readOnlyHint` annotation are untrusted;
`unknown` remains never-activatable. The acknowledgement rides the round-trip
contract.

**Why.** `API-post-search` is a read with a write-looking name; `API-move-page` is
a write with no write-looking token. Inferring an effect from a name would
auto-activate a tool on a guess (worse); silently trusting a misleading name lets
a `read` tool (no approval) execute a write. Making the ambiguity visible and
refused is the only honest option.

**Consequences.** One behavior changes: a `read` tool with a write-shaped name now
needs an acknowledgement to activate. The check is lexical, so a write hidden
behind a completely read-ish name is not caught by the name — declared effects and
per-call approvals remain the authority.

## ADR-H80 - MCP integrity: launchable presets, a per-run budget, honest truncation and lazy state

**Decision.** Four integrity gaps found by connecting real servers are closed:
(1) a `stdio` preset is a promise that clicking it works, so `presets.py`
documents that `verified=True` requires an actual launch, the offline suite
asserts each preset's shape, and the opt-in `npm run test:presets` resolves every
`stdio` package's `bin` (never in `npm test`/CI); the un-launchable `sec-edgar-mcp`
preset is replaced with the launched `@pipeworx/mcp-edgar`; (2) MCP tool calls are
capped per run (`max_calls_per_run`, default `DEFAULT_MCP_CALLS_PER_RUN`), refusing
further calls honestly with a named cap and an event; (3) a `maxTools` slice
records discovered-vs-kept and surfaces a `tools_truncated` diagnostic; (4) a lazy
server's stale cache (fingerprint mismatch) is reported as needing a connect via
`schema_cache.is_stale` rather than silently served. The test-only module
`python/harness/mcp/_testtmp.py` moved to `python/tests/_tmp_helper.py`.

**Why.** A preset that cannot run, a silent call loop, a silently truncated
catalog, and a stale cache served as declarations are all forms of a system
claiming more than it knows. The `sec_filings` preset pointed at a package with no
`bin` and no server code yet shipped `verified=True`.

**Consequences.** `manager.py` shrank (Verify → `verify.py`, rendering/session
expiry → `execution.py`) to stay under its size ratchet. The budget keys on the
run id (`"anonymous"` outside a run). The truncation guard reports counts, not the
dropped names.

## ADR-H81 - Inbound MCP notifications trigger rediscovery of one server

**Decision.** A server may add/remove/rename tools mid-session with
`notifications/tools/list_changed`, and it may change its resource/prompt listings
with `notifications/resources/list_changed` / `notifications/prompts/list_changed`.
`MCPConnection` wires the SDK `message_handler`; it acts ONLY on a list-changed
notification for a capability the server actually advertised at initialize. It
invokes one callback (`RediscoveryMixin._on_catalog_changed`) that, under the
per-server connect lock, re-runs the relevant listing through the existing path
(`MCPConnection.refresh_tools`/`refresh_listing`, which re-list on the live
session — no second discovery mechanism). For `tools` it rebuilds descriptors,
deregisters tools that disappeared, recomputes the catalog digest, re-runs every
activation gate, and re-registers survivors; for `resources`/`prompts` it replaces
the connect-time snapshot the utility tools read from (there is no activation gate
on those read-only surfaces). Every case emits a bounded, content-free
`mcp.catalog.changed` event (server id, kind, counts, and the new digest for
tools — never a description). A notification for an unknown/dead server is ignored
safely; one landing during a call cannot corrupt state (the lock).

**Why.** A changed tool set was only noticed on reconnect, so a tool the operator
approved could keep running under a stale catalog; and a changed resource/prompt
listing was served stale from the connect-time snapshot. Handling the
notifications makes both immediate.

**Consequences.** For tools, the changed digest no longer matches
`confirmed_catalog_digest`, so annotation-sourced tools become inert again until
the operator re-confirms — the existing gate, deliberately not bypassed. The
event is process-level (no run id) and published on the shared bus; the same facts
also surface on the card via `lifecycle.catalogChanges`/`removedTools`.

## ADR-H82 - A circuit breaker stops futile calls to a server that always fails

**Decision.** `circuit.py` adds a per-server breaker (CLOSED/OPEN/HALF_OPEN) with
named constants (`FAILURE_THRESHOLD=3`, `COOLDOWN_S=60`) and pure helpers
(`breaker_state`, `should_probe`) matching the `lifecycle` style. It counts calls
that REACHED the transport — timeout, session expiry, protocol/call error,
connection closed, and a provider-side error. It does NOT count: a denied/absent
approval, a caller-side validation error, a per-run budget refusal, a breaker
refusal, or a caller cancellation; those are operator/caller behaviour and must
not trip the breaker. When OPEN, a call refuses immediately and honestly with
`mcp_circuit_open`, naming the failure count, last error code and re-probe time,
and performs no transport work. After the cooldown exactly ONE probe is allowed;
success closes the breaker, failure re-arms it. An operator reset
(`POST /mcp/servers/{id}/circuit/reset`) clears it. The state is exposed in
`lifecycle.circuit` and on the card.

**Why.** `maxCallsPerRun` bounds volume and `RetryBudget` covers connect; neither
stops a server that authenticates and then fails every call, burning latency and
tokens with no signal the runtime noticed.

**Consequences.** The breaker is per server and in-process; it resets on runtime
restart. A reconnect does NOT reset the counter for free — only a successful call
does.

## ADR-H83 - The spawn-path supply-chain check fails closed on malware, open on network error

**Decision.** `supply_chain.py` queries the public OSV API for the exact package +
version about to be launched, filtering to malware advisories. It runs at the
SPAWN path only (not `Test`, not at boot for a `lazy` server), via
`screen_spawn`. A confirmed malware advisory (`MAL-` id or a malware/malicious
database type/source/summary) refuses the spawn with a diagnostic naming the
advisory id; a network error (timeout, DNS, non-200) allows the spawn and is
logged as inconclusive. Verdicts are cached keyed by `(ecosystem, package,
version)` with an absolute TTL; clean and blocked verdicts are cached, network
failures are not. A non-package runner (a real executable) is never queried. No
new dependency: the existing `httpx` client is used, and the fetcher is injectable
so the offline suite makes no network call. `audit.py` gains an
`upstream_checked` flag a caller may set; its default stays honestly offline.

**Why.** `screening.py` matches a small hardcoded IOC seed and `audit.py` is
offline; neither asks an advisory database about the code about to execute, and
`npx -y <pkg>` is arbitrary third-party execution.

**Consequences.** Fail-open on a network error is deliberate (an unreachable OSV
must not block all MCP use) and always stated, never a silent allow. The check can
only refuse on a confirmed malware advisory; an ordinary CVE is not a block.

## ADR-H84 - Sampling honours a model allowlist; tool names are clamped to the provider limit

**Decision.** `SamplingPolicy.allowed_models` (default empty) restricts which model
a server may request: with a non-empty list, a requested model not on it falls
back to the operator's configured default and increments
`sampling_model_fallbacks`; an empty list is unchanged behaviour. The runtime
continues to serve sampling on its OWN adapter (never the server's model
directly). Separately, `naming.py` clamps the assembled `mcp__<server>__<tool>`
name to `MAX_ECLIPSE_TOOL_NAME=64` characters, appending the stable identity
digest when it must shorten, so an over-long pair fails with a diagnostic at
registration instead of at the wire. A short name is byte-identical to today; the
delimiter and the `taken` collision logic are unchanged, and clamping is a last
resort surfaced as a non-blocking `note` (never a `diagnostic`, which gates
activation).

**Why.** A server asking for an arbitrary model is a small authority leak; an
over-long name failing at the wire is a confusing runtime error.

**Consequences.** No provider-specific behaviour beyond the length bound. The
name clamp cannot block a tool; it only informs the operator why the callable
name differs.

## ADR-H85 — The source-health ledger uses canonical route keys and its probes are persisted

**Decision.** A route's health entry is keyed by
`(source × market × assetClass × capability)` with every dimension normalised to
a closed vocabulary in one module (`src/lib/harness/health-key.ts`,
`canonicalMarket` / `canonicalAssetClass` / `canonicalSource`). Market is
upper-cased against the declared market set; asset class is lower-cased against
the closed enum (plus the synthetic `macro` class); anything unrecognised — or a
literal `unknown`/`*` from an instrument route — folds to the wildcard `*`, never
a persisted `unknown`. Provider/transport ids collapse to one canonical source per
provider (`safe-get`/`duckduckgo-*`/`custom-search` → `WEB`, `sec-xbrl` → `SEC`).
Normalisation is applied on BOTH write (`recordHealth`/`recordCapabilityHealth`)
and read (`sourceHealth`), so legacy rows fold onto the same key. Separately, the
`research_health` probes now write their outcomes into the same `SourceHealth`
ledger, under the same canonical route id and the same instrument-less (`*`×`*`)
key as production traffic, instead of existing only in the returned payload.

**Why.** The ledger was fragmented: the same real route appeared under `Equity`
and `equity`, under `unknown` and `*`, so per-route success rates were wrong and a
100%-healthy route could not be distinguished from a 0%-failing one. And because
the probe tested one provider (`duckduckgo-html`, `safe-get`) while production
recorded another (`WEB`), a working provider was reported as failing — the health
surface could not be trusted to decide routing.

**Consequences.** A probe run and a production run of the same capability now
increment ONE row (the P0-3 acceptance test). Route selection that consults health
can trust the keys. No schema change: capability + probe-kind are still encoded in
the existing `symbol` column. A market/class that genuinely cannot be resolved
still records — as `*`, so a failed attempt is not silently dropped.

## ADR-H86 — Retrieval planning is health-aware: a healthy route outranks a failing one

**Decision.** The Python retrieval layer reorders its planned sources using the
SAME `SourceHealth` ledger `get_source_health` reports (read through the
read-only bridge as the `source_health` capability). Ordering rules
(`python/harness/retrieval/health.py`): health is keyed by
`(source × capability × market)` with an exact-market hit preferred over a global
(`*`) route; the capability is derived from the data type and the source, so a
working quote never lends health to a statement route; **only a healthy route is
promoted** — a degraded/failing route is never demoted below an *unobserved*
route, because absence of evidence is not evidence of failure and pushing a
structured route behind generic web could invert precedence badly. The reorder is
stable (equal health keeps static order) and never adds or removes a source: it
only reorders among sources the caller already made available. The index is
fetched at most once per layer and re-read only after the D1 durable-replay check
(so a replay performs no provider work). It is fail-open — a missing bridge,
unavailable ledger or malformed row leaves the static plan untouched.

**Why.** The static plan could sit a 0%-success route ahead of an equally-eligible
100%-healthy route, so reachable data went unused — the single highest-leverage
source of missing values in the report. The evidence already existed; selection
ignored it.

**Consequences.** A healthy route is tried first and its precedence is logged and
surfaced as a warning when a planned route is recorded degraded/failing. No new
dependency. The reorder is advisory and bounded: an unobserved environment behaves
exactly as before.

## ADR-H87 - A `list_changed` with no actual change emits no event, and a silent spawn check becomes visible

**Decision.** Two reachability/honesty rules for the continuation M4/M6 work.

1. `rediscovery.py` snapshots `rt.catalog_digest` BEFORE the refresh and emits
   `mcp.catalog.changed` only when the digest moved. Discovery, the registry
   reconcile (deregister vanished tools, re-register survivors) and the
   resource/prompt listing refresh all still run on every notification — only the
   EVENT is suppressed. A `resources`/`prompts` notification is unaffected (those
   listings have no digest and no activation gate).
2. `MCPServerConfig.live_supply_chain_check` keeps its `True` default, but becomes
   a first-class operator field: `MCPServerView` / `MCPServerInput` / `DraftServer`
   carry it, `mcp-draft.ts` round-trips it with `view.liveSupplyChainCheck !== false`
   as the read rule (absent = the documented default of on), and the editor
   renders it in the Lifecycle section.

**Why.** (1) A server may announce a change that never materialises, or fire
`list_changed` gratuitously. The prior behaviour re-ran discovery (harmless) and
then emitted "catalog changed" every time, which tells the operator to re-review a
catalog that is byte-identical — the signal is only useful if it is rare and true.
(2) The check was default-on, ran on the spawn path with an 8s outbound timeout,
and was named nowhere an operator could see it. Worse, because the field was
absent from the front door's contract, a save from the editor would DROP an
explicit `false` and silently re-enable the network call — the same
field-dropping defect ADR-H74 fixed for the other lifecycle fields, reintroduced by
a new field.

**Consequences.** A gratuitous notification is now a no-op the operator never
sees; a real change still emits exactly once. The spawn check remains default-on
(the safe direction: arbitrary third-party code execution), but its cost is now
disclosable and switchable. `absent` and `true` both mean "on"; only an explicit
`false` disables it, so an older config cannot accidentally turn the check off.

## ADR-H88 - The supply-chain report surfaces the last live spawn-path verdict (derived, not a caller flag)

**Decision.** `supply_chain.SupplyChainChecker` records the last observation it
made for each `(ecosystem, package, version)` — cacheable or not — with a
human-readable `checkedAt` (wall clock, distinct from the monotonic cache clock).
A read-only lookup (`observe_command`) resolves a `command args...` spec to that
observation and NEVER queries the network. `audit.supply_chain_report` consults it
for each configured server and, when any package carries an observation, attaches
`liveVerdict` to that package and sets `upstreamChecked: true`. The
`upstream_checked` caller parameter is **removed** — the flag is now DERIVED from
real observations, so it can no longer be set by a caller that did not actually
perform a check. `GET /mcp/supply-chain` still never contacts the network; it
reports what the spawn path already observed. Per-package `liveVerdict` carries
the verdict code, advisory ids when blocked, package+version, and `checkedAt`
(identifiers only — never a response body).

**Why.** The prior contract was unimplementable: `upstream_checked=True` was
documented as "set by a CALLER that also performed a live OSV check", but no
caller existed and the only route passed nothing, so `upstreamChecked` could never
become `true`. The operator saw `offlineOnly: true, upstreamChecked: false` and
could not tell that a live check *had* run at spawn. An observation-derived flag is
the honest fix: the report reflects what actually happened, and a network failure
(the check ran but was inconclusive) is still an observation, so it surfaces too.

**Consequences.** An inconclusive (`unknown`) observation is reported but NOT
cached — a later spawn re-queries. "Never checked yet" and "checked, inconclusive"
are now distinguishable by the operator. `reset_cache` clears both the cache and
the observations. The report stays offline and read-only.

## ADR-H89 - Catalog-change counters are surfaced beside the existing banner (no event consumer)

**Decision.** The runtime keeps emitting the content-free `mcp.catalog.changed`
event and exposing `lifecycle.catalogChanges` / `lastCatalogChangeAt`. The card
surfaces those counters BESIDE the existing "catalog changed" banner, and the
lifecycle panel renders them in a small block — only when at least one change was
recorded, so a server that never changed shows no stray `0`/`—`. A single pure
helper (`mcp-draft.catalogChangeSummary`) decides what (if anything) to render.
No event consumer is added: nothing in the UI needs a live event stream, because
the change signal the operator acts on is the digest mismatch, which is already
polled with the server list.

**Why.** Two sources described one fact — the emitted event and the lifecycle
counters — and the one the operator saw (the digest-derived banner) could not say
*when* or *how often*. Adding an SSE consumer for an event nothing needs would be
a second notification system invented for symmetry. Surfacing the already-transported
counters is the cheapest honest resolution and needs no new contract.

**Consequences.** The counters are counts and a timestamp only — never a tool
description or a changed tool name. The deliberate non-goal: **no UI consumer of
`mcp.catalog.changed` was built**; the event remains available on the shared bus
for a future subscriber but is not required for the operator surface. Re-opening
that would need a concrete consumer (e.g. a global, non-per-server notification),
which does not exist today.

## ADR-H90 - Tool-call duplicate suppression is scoped to one agent step, not the run

**Decision.** In `graph.py` the `seen_calls` map that refuses a repeated
`(tool, canonical-args)` call is created INSIDE `tools_node`, so it lives for one
model turn (one agent step) rather than the whole run. Two identical calls in the
same turn keep the original behaviour exactly — the first executes, the second is
refused with the same `tool.failed`/`TOOL_FORBIDDEN` event and the same
"Use the earlier result" message shape. A call repeated in a LATER turn executes
again. The key remains `(name, _stable_key(args))`; it is deliberately NOT keyed
on the assistant message id (the same model message can legitimately recur across
steps, which would reintroduce the bug).

**Why.** The guard's purpose is to stop one turn from issuing the same call twice.
A run-scoped map also blocked a legitimate re-issue in a later turn and instructed
the model to reuse a stale result — the next page of a paginated listing,
re-polling a price after new evidence arrived, a deliberate retry after a
transient failure, or a second lookup whose first result changed between steps.
Those are correct model behaviours that the run-scoped map silently defeated.

**Consequences.** A cross-turn re-issue does not multiply upstream network calls:
the retrieval layer still deduplicates identical data fetches per run through the
shared `retrieval_cache` passed into `build_graph`. The duplicate refusal still
counts as a tool error and consumes the run's `max_tool_calls` budget — that
accounting is unchanged and out of scope here (recorded as an observation, not
changed). Rejected alternative: keying on `(step, name, args)` — functionally
equivalent but leaves a growing per-run map whose entries are never read again;
resetting the map per `tools_node` call is simpler and self-evidently step-scoped.

## ADR-H91 - Native tool-result text is bounded at the single execution seam and reports its own truncation

**Decision.** `ToolRegistry.execute` — the one seam every native and MCP tool
passes through — bounds a tool's model-facing text to
`MAX_TOOL_RESULT_CHARS = 24_000`. Over the bound the text is cut and a clearly
non-JSON trailer names the shown and total sizes; `ToolResult` gains
`truncated` / `shown_chars` / `total_chars`, and the graph emits a
`tool.truncated` event (sizes only, once per trimmed result). Under the bound the
text is byte-identical — no marker, no flag, no whitespace change. `ToolResult.data`
(the structured payload the front door reads) is NEVER bounded.

**Why.** A native tool with no internal cap had neither a ceiling nor a signal: its
result was appended verbatim into the model's context. The value is tied to the
measured budget, not chosen arbitrarily: at `CHARS_PER_TOKEN = 4` the bound is
~6 000 tokens; `graph.MAX_HISTORY_CHARS = 40_000` bounds the WHOLE conversation,
so one tool result must be a fraction of it; and
`research.synthesis.MAX_PACKET_CHARS = 24_000` is the largest synthesized evidence
packet the runtime already accepts, so a single raw result has no reason to exceed
it. The marker cannot parse as JSON, so a truncated JSON body can never be
mistaken for a complete one — the exact failure mode avoided.

**Consequences.** Blast radius measured: exactly one native tool can exceed the
bound today — `session_open`, which returns a bounded message WINDOW with no
character ceiling (a maximal 30×3 000-char window is 25 612 chars → trimmed to
24 000). The constant is deliberately NOT raised to hide it; a bound that hides
the one tool it exists to catch would be pointless. Rejected alternative: a
per-tool `max_result_chars` field — more knobs, and a new tool could still forget
one; a single global seam cannot be bypassed by omission.

## ADR-H92 - An effectful-tool approval is single-use

**Decision.** An `McpApproval` authorizes exactly ONE call. Authorization CLAIMS
the approval with a guarded `UPDATE ... WHERE id=? AND status='approved'` and a
rowcount check (`ApprovalStore.consume`), moving it to a terminal `consumed` state
and stamping `usedAt`. A second identical call cannot be authorized by the same
approval: it creates a fresh PENDING request and is refused (never a silent pass,
never a bare denial with no record). `is_authorized` remains a NON-consuming probe
for the resource/prompt paths and tests; the authorizing path is `consume`. Because
one effectful call is authorized at two seams (the registry gate and the MCP
manager's `_execute` re-assert), the first successful claim records the authorized
argument digest on the shared `ToolContext` for the current call-scope, so the
second seam authorizes without consuming again; the registry clears that scope at
the start of each tool call, so every new call must claim its own approval.

**Why.** One operator approval previously authorized an UNBOUNDED number of
identical effectful calls for up to the TTL (15 min default, 24 h max), each
emitting `mcp.tool.approved` as if freshly decided — a silent semantic the module
docstring never stated. Single-use matches the store's fail-closed posture (no
model/server-settable authority) and needs no new operator-settable field. Rejected
alternative (Option B): an explicit, operator-only repeatable/standing grant with
a `singleUse` field and its own UI label — a larger surface that adds a
dangerous-by-default-if-misread toggle for no demonstrated need; single-use is the
safe default and a standing grant can be added later as an explicit, labeled
decision.

**Consequences.** The `consumed` status and `usedAt` ride the whole round-trip:
the Python row + `_row()`, the `GET /mcp/approvals` response, `MCPApprovalView` in
`mcp-types.ts`, and the approvals UI (a `consumed` filter, a distinct badge, and a
"consumed" line). Every existing invariant is preserved: unknown effects are never
approvable; the digest still binds the arguments; TTL expiry and terminal denial
are unchanged; a prior approval/tool description/model claim still cannot
authorize a different action. A `consumed` approval is not re-used by `request`
(which now returns a fresh PENDING row instead of an already-approved one).

## ADR-H93 - Run lineage, durable checkpoints, and idempotent resume

**Decision.** A run now has an identity that survives a crash. `HarnessRun` gained
`parentRunId`/`workflowId` (the run that spawned it and the workflow it belongs
to); a new `RunCheckpoint` table stores a BOUNDED per-boundary reference (after
each completed agent step, each tool-result batch, and at terminal status) and a
new `ToolExecutionIdempotency` table records one row per executed
`(runId, stepIndex, toolCallId)`. `POST /runs/{id}/resume` re-enters the graph at
the recorded node and REUSES a recorded tool result instead of re-running it; a
resume with no checkpoint is `CHECKPOINT_NOT_FOUND` and a resume of a terminal run
is `RESUME_CONFLICT` — never a fresh run in its place. The persistence lives in a
new `python/harness/run_lineage.py` bound to the ONE store connection (same
pattern as `mcp/approvals.py`), so ratcheted `persistence.py` did not grow.

**Why.** There was no run lineage and no checkpoint anywhere in the Python
runtime, and the only "checkpoint" concept was the TypeScript conversation store.
Every later phase (workflow steps, approval resume, observability) needs a run
whose parent and progress survive a restart. The checkpoint is a REFERENCE, not a
second trace: the message tail is capped (≤60 messages, ≤12k chars each) and the
allowlist/pending-calls are capped, because a checkpoint that duplicates the event
log is a new god table.

**Consequences.** `RunResult` gained `parentRunId`/`childRunIds`; a skill child-run
records its parent. Resume is safe for side-effecting tools by construction. A
downgrade ignores the new tables/columns (idempotent stdlib DDL).

## ADR-H94 - The route-health report is a summary partition, and the declared list is withheld by default

**Decision.** `sourceHealth()` returns a compact SUMMARY HEAD first (recorded route
counts by health class, markets with any recorded attempt, first N recorded rows)
plus the live recorded rows; the ~1,200-row declared universe is WITHHELD and only
returned for `recordedOnly: true` or `includeDeclared: true`. The Python
`get_source_health` renders the head, states the withheld count, and how to request
the full list. `capabilityMatrix()` canonicalises its market key exactly as
`sourceHealth()` does. `SourceHealth` gained `lastSuccessAt`/`lastFailureAt`.

**Why.** The recorded ledger is real and correct but was UNREACHABLE: the declared
list was emitted BEFORE any recorded row, so at the 24k tool-result bound a caller
only ever saw "unknown — 0 ok / 0 fail" rows and concluded nothing had ever run. A
working system therefore looked dead. The honesty semantics are unchanged: a
declared route with zero attempts is `unknown`, neither healthy nor failing.

**Consequences.** Two readers of one ledger now agree on the route key. A
one-time migration (`scripts/migrate-source-health-canonical.ts`) folds legacy rows
(including a literal `unknown` in source/market) onto canonical keys; a DB-level
test asserts no literal `unknown` remains. The new columns are nullable and
additive.

## ADR-H95 - The capability matrix cannot assert an impossible fact; the market set is 34

**Decision.** `buildCapabilityMatrix` reconciles every axis: a non-`unknown`
observation against an unimplemented level is REPRESENTED as `matrixInconsistent`
with a reason (level forced non-implemented), never smoothed over. CH/KW/QA are
declared COVERAGE entries with their REAL ISO currencies (CHF/KWD/QAR) and a
declared blocker (decision D1: keep the real venues). Provider eligibility is
DECLARED (`provider-eligibility.ts`) rather than inferred from a `supports: () =>
true`; a declared `not_eligible` market is not configured on the quote axis and is
tagged `secondary`. The market count is 34 and asserted in a test.

**Why.** `capability.ts` could render `quote: not implemented (observed: working)`
in the same row (a UK yfinance quote succeeded while UK is absent from
`MARKET_SLUG`), and a market outside the COVERAGE registry reported a USD currency
it does not use. The real limit on a quote route is data/symbol quality (`.NG`,
`.AE` return quote-not-found; `.ME`/`.JO`/`.VN`/`.MX` are thin), not the absence of
an adapter — so the fix is declared eligibility plus a verified sample symbol.

**Consequences.** A capability-matrix eval gate (Phase 8) fails the build on any
regression. DERIV (recognised, uncovered) never claims `configured` on any axis,
including web.

## ADR-H96 - The workflow compiler reuses the one execution plane and never inherits tools across steps

**Decision.** A versioned, bounded `Workflow` compiles onto the EXISTING
`execute_run` graph (`python/harness/workflows/`); it does NOT build a second
agent loop, tool registry or model adapter. A step's effective tool scope is the
INTERSECTION of the agent allowlist and the step's declared tools, enforced at the
SAME `ToolRegistry.execute(allowed=...)` seam (a denied call is a structured
`TOOL_FORBIDDEN`). Approval steps reuse the existing single-use `ApprovalStore`.
The path is flag-gated (`HARNESS_WORKFLOWS_ENABLED`, default OFF); a run with no
`workflowId` is unchanged.

**Why.** The runtime already IS a harness — one execution plane, one registry, one
allowlist seam, one bus, one persistence layer. What it lacked was orchestration ON
TOP of that plane. Per the coding-agent capability contract, agents must NOT
inherit each other's tools or access: a step can only NARROW its scope, never
widen it. A cycle, an unbounded fan-out, an out-of-scope tool, and a step with no
terminal path are each rejected at validation with a NAMED reason.

**Consequences (non-goals).** No visual workflow designer, bot scheduler, or
agent-builder UI (roadmap Phases 8-9). `execute_run` is wrapped, not replaced.

## ADR-H97 - The code capability is tools on the one registry, not a second runtime

**Decision.** The whole code capability (roadmap Phases 1-12) is delivered as
new TOOLS on the EXISTING `ToolRegistry`, driven by the EXISTING `execute_run`
graph — never a second agent loop, tool registry or model adapter. Phase 0 ships
the policy authority (`python/harness/code/policy.py`) and a workspace-bound
actor class (`skills/permissions.Actor` gains `workspace_id`/`autonomy`), and
NOTHING executable: no filesystem, shell, patch or exec tool — not even a stub.

**Why.** The runtime already is a harness: one execution plane, one registry,
one allowlist seam, one bus, one persistence layer (README §3.1, ADR-H96). A
second runtime would fork every one of those surfaces and double the failure
modes on a finance system. The blocker is policy, not architecture: `code.write`
sat in `FORBIDDEN_PERMISSIONS` and `code.execute` in `BLOCKED_PERMISSIONS`
(ADR-025), so the capability was impossible by accident. Phase 0 turns that
into a deliberate, tested decision — a second actor class that can hold the code
verbs ONLY when a run is bound to a workspace and carries an autonomy profile —
so a coding agent can no longer "fix" a failing permission test by deleting a
constant.

**Consequences.** New code verbs live in `CODE_PERMISSIONS` (manifest) and are
grantable only through `code/policy.code_grants(autonomy)`; `FORBIDDEN_PERMISSIONS`
narrows to trade/broker/production. The default actor (`DEFAULT_ACTOR`) and the
operator actor (`OPERATOR_ACTOR`) hold no code verb, proven by a test and a
gate. A caller-supplied operator grant can no longer smuggle a code verb in.

## ADR-H98 - `code/policy.py` is the single policy authority; autonomy profiles are enforced in code

**Decision.** `python/harness/code/policy.py` is the ONE place a code-policy
decision is made: may this run read/write/execute this thing, in this workspace,
under this autonomy profile? It owns the three autonomy profiles
(`plan_only`, `edit_verify`, `approve_external`) as data, `code_grants()` maps a
profile to its verbs, and `decide_write` / `decide_command` are the only
decision functions. Every later phase imports these rules; none re-implements
them. `skills/permissions.Actor.granted()` unions `code_grants(autonomy)` ONLY
when both a `workspace_id` and an `autonomy` are set.

**Why.** Prose is never a security boundary (README §3.2). The permission model
must be readable as code, reviewable, and testable in isolation. An unknown
autonomy string grants NOTHING (fail-closed), mirroring the MCP `trust` tier — a
typo in a profile name can only lose capability, never gain it. Keeping the
decision in one module (the same pattern as `skills/permissions.py` for skills)
means Phase 10 can FREEZE `code/policy.py` as a protected path without leaving a
second, un-frozen copy of the rules behind.

**Consequences.** The code verb set is derived, not enumerated at each call
site. `POLICY_DENIED`-style decisions carry a stable machine `code` plus ONE
plain sentence (`PolicyDecision.reason`) safe to show a human. Autonomy profile
names are mechanism vocabulary and must never appear in a user-facing string
(ADR-H99 / `PLAIN_LANGUAGE_DENYLIST`).

## ADR-H99 - Protected paths, command classes, default-deny network and secret posture

**Decision.** The code capability's safety data lives in `code/policy.py` as
tables: `PROTECTED_PATHS` (never touchable, even inside a workspace and even by
an operator — `jdds.db`, the memory DBs, `.env`, `mcp-servers.json`,
`prisma/migrations/**`, `.git/**`, the frozen policy/permission/approval/gate
files, and key material), `IGNORED_DIRS`/`IGNORED_GLOBS`, `COMMAND_CLASSES` (a
closed tuple whose per-class program sets are declared, with a `DENIED_PROGRAMS`
belt-and-braces list), `NETWORK_DEFAULT = False`, and
`SECRET_ENV_ALLOWLIST` (every other environment variable is dropped from a child
process — never an `os.environ` passthrough). Path safety is by construction:
`resolve_within` compares REAL paths and refuses traversal, an absolute path
outside the root, and a link that leaves the root; the raw string is never
trusted. Protected outranks ignored, so a protected path always reports
`PROTECTED_PATH`.

**Why.** Isolation must exist BEFORE any write/execute tool is opened (README
§2, ordering rule). A denylist of prose is not enough: the protected set has to
be data a test can assert against and a later phase can freeze. Default-deny
network and an explicit secret allowlist are the same discipline — an unknown
class or a shell/downloader binary is refused rather than permitted by
omission. `PLAIN_LANGUAGE_DENYLIST` is the mechanism-word list every
user-facing gate reads from ONE place.

**Consequences.** Phase 3 implements `COMMAND_CLASSES` and owns the argv
templates; Phase 10 freezes `policy.py`. A missing isolation primitive produces
an honest refusal (`SANDBOX_UNAVAILABLE`), never a degraded unsandboxed run
(README §3.5). Every refusal sentence is asserted, by a Phase 0 test, to be one
sentence with no denylist term — the seed of the per-phase plain-language gates.

## ADR-H100 - Read-only repository navigation is path-confined, bounded and citable

**Decision.** Phase 1 adds exactly FIVE read-only tools on the ONE existing
`ToolRegistry` — `workspace_status`, `workspace_list`, `workspace_search`,
`workspace_read`, `workspace_docs` — every one `permission="read"`, `risk="low"`.
There is no write tool, no patch tool and no command runner; the ONLY child
process is a fixed, argument-free `git` read probe. The navigator is a SEPARATE
agent preset (`code-navigator`) whose allowlist is only those five tools and which
does NOT set `allowMcpTools`, so it can never reach a finance tool or an MCP tool.
Confinement is owned by `code/workspace.py::confine`, which CALLS the Phase-0
`policy.resolve_within` (it does not re-implement it) and maps its denial to a
distinct structured code per escape vector (`PATH_TRAVERSAL`,
`PATH_OUTSIDE_WORKSPACE`, `SYMLINK_ESCAPE`, `PROTECTED_PATH`, `IGNORED_PATH`,
`NOT_FOUND`). Every read is line-numbered with a `nextStartLine` continuation
offset, refuses binary files, and redacts secret-shaped lines to `«redacted»`
through the ONE pattern set (`session_index.redact_span`); `workspace_search` is
bounded by matches, files, bytes and a wall-clock deadline (partial results are
marked truncated), and `workspace_docs` reuses the session-search tokenization
and ranking as a bounded per-call scan of `docs/**` — no table, no index, no
vector store. `workspace_read` reports `PROTECTED_PATH` for `jdds.db`, not
`BINARY_FILE`, because protected check precedes the binary probe.

**Why.** The runtime had no way to see the repository at all; every "where is X
documented" ended at prose. The read half is safe to open first because the
registry already refuses any non-read tool without an authorizer, so a phase made
only of read tools needs no approval machinery. Path safety must be ONE seam: a
second traversal check would drift from the Phase-0 authority and become the
weaker one. Reusing the session-index secret patterns means a file reader cannot
become a new leak path with its own, divergent denylist. And the docs search must
not become a second indexer — the roadmap's whole-project non-goal — so it scans
per call and reports its engine honestly.

**Consequences.** `confine` is the only place a code path is resolved (a grep for
`realpath` under `python/harness/code/` hits only `workspace.py`; `subprocess`
only `workspace.py`). `RunRequest.workspace` is an optional, additive
narrowing/confirmation: a caller's `root` must realpath to the server-resolved
root or the run gets no workspace, so a request field can never point the
navigator at a different directory. `ToolContext.workspace` carries the binding
(one graph line). User-facing copy lives in `src/lib/i18n/` (only `task.*`/
`refusal.*` keys added) and the code→sentence map is data; the jargon gate
`src/lib/i18n/plain-language.test.ts` scans the values. Phase 2 builds the write
half on this same confinement and the same preset discipline.

## ADR-H101 - Workspace isolation: disposable worktrees, snapshot fallback, never the user's own checkout

**Decision.** Phase 2 lets Eclipse author a change — create/replace/delete/move a
file — inside a DISPOSABLE copy of the repository, never the operator's checkout.
`code/worktree.py` allocates at `<root>/.black-eclipse/code-workspaces/<id>` (an
already-gitignored scratch root) with `git worktree add --detach`; when git
`worktree` is unavailable it falls back to a bounded snapshot copy and reports
`strategy: "snapshot"` honestly on the record and the event. The root is resolved
INTERNALLY (`workspace.default_root()`) — it is never an argument to any function
in `worktree.py`, so no caller can name the checkout. `release` refuses to delete
anything whose realpath is not under the scratch root (`RELEASE_OUTSIDE_SCRATCH`)
and is idempotent. The patch engine (`code/patch.py`) copies the discipline of
`skills/patches.py`: a closed op set, structural validation BEFORE any write, a
content-hash stale-base refusal (`PATCH_BASE_MISMATCH`), a unique-span rule for
`replace` (0 → `PATCH_SPAN_NOT_FOUND`, 2+ → `PATCH_SPAN_AMBIGUOUS`; never a blind
`.replace()`), and ATOMICity — a refusal at any op applies NOTHING. Every applied
op records `contentHashBefore`/`After`. Three tools join the registry:
`workspace_patch_apply` (`permission="write"`, `effect="write"`), `workspace_diff`
(`permission="read"`), `workspace_revert` (`permission="write"`). A write is
authorized by the run's autonomy profile (`edit_verify` grants `code.write`),
composed into the single effect authorizer; `git.write` is implemented nowhere.

**Why.** The whole value of the capability is that it can change code; the whole
risk is that it changes the WRONG copy. The concurrency rule (README §4) makes
this concrete: OpenCode edits the same tree, so a write tool that touched the
checkout would collide with a live session. A detached worktree makes that
impossible by construction, and putting it under the ignored `.black-eclipse/`
means a leaked workspace can never become a tracked artifact. The stale-base and
atomicity rules exist because a half-applied patch is exactly the "silently
rebased" failure the skill engine already refuses; a content hash generalizes a
version string to a file. The refusal vocabulary is the same per-vector honesty
Phase 0/1 established, so a caller (and a test) can tell an escape from a
protected path from a stale base.

**Consequences.** `python/harness/code/store.py` owns the `CodeWorkspace` table in
`agent-memory.db` bound to the one `AgentMemoryStore` connection (the
`run_lineage.py` pattern), so the ratcheted `persistence.py` does not grow and no
second database appears. `sweep_expired` runs on the existing startup lifespan,
releasing workspaces past the TTL so a cancellation leaves no orphan. Front-door
copy lives in `src/lib/i18n/` (`task.authoring.*` progress/result lines plus a
`refusal.*` code→sentence map as data), and the jargon gate scans it. `git.write`
remains an operator action; Phase 5 is where an agent-side `git.write` could be
introduced behind a single-use approval.

## ADR-H102 - Commands are a closed table; a missing isolation primitive refuses rather than degrades

**Decision.** Phase 3 lets the agent run allowlisted checks through a single
execution primitive. `code/commands.py` is a closed TABLE of command classes:
the model supplies a class name plus typed args, never an argv. An `ArgSpec`
validates each argument with `re.fullmatch` (and refuses a `..` component); the
argv is assembled from a fixed template whose first token is an absolute,
closed executable from `EXECUTABLES` (npm/npx/node, the VENDORED
`scripts/vendor/python/python.exe`, and git). `git_read.subcommand` is a CLOSED
allowlist — `push`, `reset`, `clean`, `checkout`, `commit`, `config` are absent
by construction. `dependency_install` is the only class with `network=True`, is
operator-gated (default OFF), and uses `--ignore-scripts`. `code/sandbox.py` is
the ONE execution seam: `build_env` copies ONLY `policy.SECRET_ENV_ALLOWLIST`
(never `os.environ`, so `HARNESS_*`/`CRON_SECRET` are absent), `cwd` is the
resolved worktree root, `shell=False` always, a wall-clock timeout kills the
whole process TREE, output is capped with honest `truncated`/`totalChars`, and
cancellation propagates with no retry. On Windows the child is assigned to a
Job Object with `KILL_ON_JOB_CLOSE` (plus a deterministic `taskkill /T`); on
POSIX it gets its own process group. If no primitive exists, `select_backend`
raises `SandboxUnavailable` and the command is REFUSED — never run unsandboxed.
`command_run` is a registry tool (`permission="write"`,
`effect="external_action"`); the handler enforces the autonomy profile
(`command.execute`) and records EVERY attempt — including every refusal — as a
`HarnessCommandExecution` row plus a `command.*` event.

**Why.** Executing code is where a mistake stops being a bad diff and becomes a
bad side effect, so this is the strictest phase in the roadmap. A matcher over
model-supplied strings is a policy surface that grows with every string; a table
is closed, reviewable, and its size is the size of the capability. The repo's own
standard for spawning a child (MCP) already requires argv arrays, an explicit env
allowlist and platform-appropriate reaping, so the broker matches it rather than
inventing a weaker rule. And the honesty rule is already law (a missing runtime
fails with 503, never a fake agent) — the same rule applied to isolation: no
primitive means refuse, not degrade. Auditability is the point: a block that
leaves no row and no event is treated as a FAILURE, because a refusal a user
cannot see is indistinguishable from a silent success.

**Consequences.** `code/store.py` (not the ratcheted `persistence.py`) owns the
`HarnessCommandExecution` DDL and helpers on the one `AgentMemoryStore`
connection. Every refusal carries a machine code AND one plain sentence plus a
recovery step (`commands.COMMAND_REFUSAL_COPY`, mirrored in `src/lib/i18n`), and
the plain-language gate asserts neither leaks a mechanism word. NETWORK is denied
by CLASS and by a scrubbed environment (proxies dropped); there is no OS network
namespace in this phase, which is recorded as a known limit — a command that
tries to reach the network fails because the class is refused or the route is
unreachable, and the attempt is recorded. Phase 4 consumes the recorded
executions to prove a "pass" with an executor-backed receipt.

## ADR-H103 — The system prompt is hardened and given a run-scoped clock; the cache key covers prompt content

**Decision.** The Eclipse Agent system prompt is a reduction-and-accuracy surface,
not a capability surface. Four properties now hold. (1) A run-scoped
`runtime_context` `PromptSegment` carries the run's real date, time and UTC offset
(`prompt_segments.runtime_context_block`) and is rendered as its OWN per-run
`SystemMessage` after the byte-stable system head, never inside it; it has its own
content hash and is excluded from `STATIC_SEGMENTS`, so the stable prefix still
caches and the run date never invalidates it. (2) `prompt_cache_key` now includes
the CONTENT hash of every reusable (`STATIC_SEGMENTS` = `system_policy` +
`agent_identity` + `tool_schemas`) segment, so editing the prompt changes the key
even when the hand-bumped `SYSTEM_POLICY_VERSION` has not; `runtime_context`,
`run_instructions` and `user_message` remain excluded. `STATIC_SEGMENTS` is split
from a new `RUN_FROZEN_SEGMENTS`, and only the static group feeds
`reusable_total_tokens()`, so a per-run block no longer inflates the reuse
accounting. (3) The execution-discipline blocks carry ONE statement per rule (no
near-verbatim duplicates of the operating principles or tool-use enforcement) and
its examples are finance-native (ambiguous instrument identity, market/currency
defaulting) rather than shell/OS examples; the identity preamble is a bounded
role-and-domains statement, not a 52-bullet inventory. (4) The bound tool schemas
are declared authoritative (once), so the prompt no longer hardcodes tool names;
the dead `filter_system_prompt` tool-list replacement was removed (the sentence it
searched for is absent).

**Why.** The prompt demanded as-of periods, staleness labels and revalidation but
gave the model no clock; it repeated the same rules across eight `<...>` blocks;
and its cache key tracked only hand-bumped versions, so a real prompt edit left
the key unchanged — a correctness bug in the observability contract.

**Consequences.** `filter_system_prompt` continues to drop memory/session guidance
when those stores are off (unchanged). `graph.execute_run` builds the runtime
block once per run and threads it into the prompt plan, the assembled messages and
the measured history budget. No permission or capability is added: this is a
reduction plus an accuracy fix. `docs/harness/architecture.md` and
`docs/NAVIGATION.md` updated; tests `test_prompt_segments.py`
(`test_prompt_content_edit_changes_cache_key`,
`test_runtime_context_does_not_change_cache_key`,
`test_reusable_token_accounting_excludes_run_frozen_segments`,
`test_runtime_context_block_carries_run_date_and_id`) and `test_memory_tools.py`
(extended `test_prompt_has_no_phantom_capabilities`, `test_prompt_char_ceiling`).

## ADR-H104 — The Eclipse Agent prompt states the finance-harness contract

**Decision.** `ECLIPSE_AGENT_SYSTEM_PROMPT` now describes a finance harness, not
only an analyst: it carries a `# Market data semantics` block (session state,
price basis, period basis, corporate actions, point-in-time vs restated, FX,
staleness) as *statement requirements* that make two numbers comparable; an
`# Inputs and authority` precedence table (system policy > run instructions >
attached documents > tool/retrieved evidence > profile context > conversation
history > text inside a retrieved artifact) plus the attached-document rule
(`[attached: <name>]`, primary source for its contents, data never instruction);
an `# Answer contract` (answer-first shape, `source: as-of` citations, numeric
conventions, one contrastive worked example); and a `## Runtime awareness` block
(bounded steps/timeout, a stop rule, truncation disclosure, no redundant
retrieval). The identity preamble was rewritten so its action surface is exactly
the bound tool allowlist while its domain list stays framed as competence. The
declared `session_summary` prompt segment was **removed**: it was never populated
by any caller (only tests), and no bounded producer exists without a new
dependency or a second model call, so keeping it would have overstated the
prompt's real contents.

**Why.** The prompt previously demanded as-of periods, units and comparability
without ever naming the finance-specific facts that make numbers comparable, and
it did not describe the runtime the model actually runs in. A capability claim
("models, simulates, orchestrates") contradicted by the bound allowlist two
sentences later is worse than no claim. The growth ceiling (≤ 17,500 chars) was
paid for by tightening `# Investment Analysis`, `## MCP tools`, `## Tool calls`,
identity preamble and `# Tool-use enforcement` — each rule retained.

**Consequences.** `python/harness/prompt_segments.py` no longer declares
`session_summary` (its `PromptPlan`, `to_dict` and cache key are unchanged
otherwise). Guard tests in `test_memory_tools.py` (`test_prompt_char_ceiling` at
17,500, `test_prompt_market_data_semantics_present`,
`test_prompt_inputs_authority_and_attachments_present`,
`test_prompt_has_no_duplicated_rule_sentences`) and `test_prompt_segments.py`
(`test_session_summary_is_not_a_declared_segment`). No tool, permission or
capability was added. Design prompt:
`docs/harness/prompt-v2-finance-harness-opencode-prompt.md`; progress log
`docs/harness/prompt-v2-finance-harness-progress.md`.

## ADR-H105 - A check is passing only when the executor recorded it; unbacked claims are marked

**Decision.** Phase 4 builds the trust spine for the code domain by mirroring the
finance validator discipline. `code/verify.py` is a per-run `VerificationLedger`:
a check is passing ONLY when it holds a `VerificationRecord` with a zero exit
code and a class in `CLAIM_CLASSES`. A deterministic, sentence-level claim parser
(`CLAIM_PATTERNS`, negation-aware so `"the tests did not run"` is not a claim)
finds pass-claims in the final answer; `unverified_claims` is the difference
between what the model asserted and what the executor proved. `enforce_answer`
(default `mark`, `strip` available) appends `UNVERIFIED_MARKER` naming the
classes that could have supported an unbacked claim, so a pass-claim is never
rendered as fact. `code/repair.py` runs plan -> edit -> check -> repair bounded by
`RepairBudget` (attempts, wall-clock, cost), checked BEFORE every edit; on
exhaustion it STOPS and reports the failing class + output digest. A
`SANDBOX_UNAVAILABLE` check is `refused`, never a pass. `execute_run` CALLS both
(no new graph node); the ledger is rehydrated from `HarnessRun.codeVerification`
on resume (EMPTY when absent) and persisted from `code/store.py`. Six
deterministic mistake categories read the blob + events. `output_digest` hashes
the FULL normalized output (CRLF/trailing-whitespace independent).

**Why.** The finance path is believable because a claim is checked against a
record: retrieval -> coverage -> validator -> receipt. The code path had no
equivalent, so a model could write "all tests pass" whether or not a test ran —
and prose is not a security boundary (README §3.2). A deterministic check must own
the decision; the model may propose a repair but never decides whether a check
passed. Bounding the repair loop is the whole point: an unbounded retry is the
failure mode this phase exists to prevent.

**Consequences.** A passing claim is provably impossible without a zero-exit
record (`supported = True` has exactly one assignment site, behind `passed`). The
`codeVerification` blob is additive and old-row-safe; `persistence.py` stayed
within its ratchet by putting the column DDL in `code/store.py` (the
`run_lineage.py` precedent). The UI panel is titled "Proof it works" and renders
plain lines with the mechanism behind a details affordance; the jargon gate
scans it. The eval pack (`python -m harness.code.eval`) floors
`falseVerifiedRate` at 0. Phase 5 may grant autonomy because output is now
verifiable.

## ADR-H106 - A prompt must describe its own allowlist; ranked authorities need a producer

**Decision.** Two rules are now enforced by guard tests over BOTH agent presets
(`python/tests/test_memory_tools.py`). (1) **Prompt/allowlist agreement:** every
tool a prompt names as its own must be in that preset's allowlist, and a prompt
may not deny a capability its allowlist contains; the check that a prompt which
enumerates its tools names all of them. (2) **No phantom authority:** the
`run instructions` rank was REMOVED from the `# Inputs and authority` table
(renumbered 1–6) and the `run_instructions` prompt segment was removed from
`prompt_segments.py`. There is no producer for it anywhere in the runtime (no
`schemas.py` field, no TS bridge field, and the sole `build_prompt_plan` caller
never passed it); ranking it above attached documents and profile context
elevated a source that never arrives. Also fixed: the Repository Navigator
prompt, which claimed exactly five read tools and "cannot run any command" while
`CODE_NAVIGATOR_TOOLS` has nine including `command_run` and the three authoring
tools.

**Why.** Gap 1 was a real correctness bug in the *navigator* prompt, not the
finance one: `command_run` + `## Running checks` landed in the same wave as older
prose saying "you cannot run any command", so the prompt described three
mutually-inconsistent surfaces. That is a class — any time an allowlist grows the
prompt describing it can silently go stale — so the durable fix is the guard,
not the one edit. Removing rather than wiring `run instructions` follows the
session_summary precedent and the constraint against adding input surfaces.

**Consequences.** `prompts.py` (both prompt strings), `prompt_segments.py`
(`run_instructions` removed from `PromptPlan`, `RUN_FROZEN_SEGMENTS`, the
segment list and the cache-key docs), and the guard tests. No tool, permission or
capability changed; the navigator's allowlist was NOT widened to match the
prompt — the prompt was corrected to match the allowlist. `## Running checks`
honesty rules are unchanged. Progress log:
`docs/harness/prompt-followup-progress.md`.

## ADR-H107 - One approval store, generalized; a code action is single-use, digest- and workspace-bound

**Decision.** Phase 5 adds the coding agent, and the external actions it may take
under `approve_external` (commit, push, open a PR, deploy) reuse the ONE approval
mechanism rather than a second one. Concretely:

  * The autonomy profile is enforced by the **tool allowlist**, not a prompt.
    `code/policy.allowed_tools(autonomy, declared)` is the ONE place a
    write/external tool is removed; `graph.effective_allowlist` calls it before
    the model sees any schema. At `plan_only` the write tools are absent, so a
    model that "decides" to write cannot: the registry returns `TOOL_FORBIDDEN`.
  * The `McpApproval` store is GENERALIZED into one approval concept with a
    `kind` discriminator (`"mcp_tool"` | `"code_action"`). `McpApproval` stays the
    physical home (existing MCP rows need no migration) and `kind`/`workspaceId`
    are additive columns (`kind` defaults to `"mcp_tool"`). The guarded-claim
    logic ADR-H92 froze is lifted into ONE function, `mcp.approvals.claim_guarded`,
    used by both kinds.
  * A code action is a `CodeActionRequest` whose canonicalized payload INCLUDES
    the workspace id, so an approval for a commit in workspace A can never
    authorize the same commit in workspace B. `code_action_digest` reuses
    `mcp.approvals.args_digest`, so the two kinds cannot disagree about what "the
    same payload" means.
  * The four action tools are `permission="write"`, `effect="external_action"`,
    carry an `actionKind` in `effect_metadata`, and are resolved by
    `code.actions.make_code_action_authorizer`, which consumes the approval ONCE
    (emitting `code.action.approval_required` / `code.action.approved`).
  * The task lifecycle is a CONSUMER of `run_lineage.py`: a code task IS a run,
    and its boundaries (`task.created`, `plan.accepted`, `patch.applied`,
    `command.executed`, `task.cancelled`, `task.discarded`) are `RunCheckpoint`
    rows. Resume reads `latest_checkpoint()` and reuses the recorded tool result
    (`was_tool_executed`), so it never re-applies a patch or re-runs a side-effect.

**Why.** Autonomy must be structural: a prompt instruction is not a boundary
(README §3.2), and the allowlist is the one seam the registry already enforces.
The approval question was open (generalize vs sibling) and leaving it open risks
two single-use implementations that silently drift — exactly the "two
half-systems" the roadmap forbids. Rejected alternative: a sibling `CodeApproval`
table. It would duplicate the guarded `UPDATE ... WHERE status='approved'`
rowcount check that makes an approval single-use, and a drift between the two
copies is a silent authorization bug. Reusing `run_lineage.py` for the task
lifecycle is the same discipline: Phase 5 is a consumer, not a builder.

**Consequences.** `main.py` grew by exactly two lines (an import and
`include_router(code_router)`). Every mutating `/code` route carries
`require_operator` (loopback or the runtime secret; never a body boolean). The
finance agent is unchanged and holds no code tool; the code agent holds no finance
tool and does not set `allowMcpTools`; the ADR-H92 MCP approval tests remain the
regression suite and stay green. The task surface is plain language ("Just tell
me what you'd do" / "Make the change and show me" / "Do it and ask me before
anything outside the app"), and the jargon gate scans it. Phases 6, 7, 8 and 9 may
now build on a code-capable agent with a task lifecycle.


## ADR-H108 � Harness-owned jobs; the TS refresh loops stay as they are

**Decision.** Phase 6 adds a durable, single-process job model to the Python
harness (`python/harness/jobs/`) beside the three existing TypeScript schedulers.
It does **not** replace or modify `src/lib/scraper/scheduler.ts`,
`src/lib/connectors/refresh-scheduler.ts` or `src/lib/investor-eye/scheduler.ts`.

A job is durable, reviewable **DATA** (`JobDefinition` on the `HarnessJob` table,
with a `HarnessJobRun` history table, both in `agent-memory.db`). A job references
a skill (by id + pinned version) or an objective + agent id; it never holds
executable code and never widens authority. A job run **is** a normal `execute_run`
with a job id attached � there is no second agent loop, tool registry or model
adapter (README �3.1). The run row links to the existing `HarnessRun`, so a job
produces the same trace, events, tool executions and (for a code job) verification
ledger as a user-initiated run.

The scheduler is one FastAPI-lifespan task started in `service.start_jobs()`
alongside `start_mcp()`. It reuses `mcp/circuit.py`'s breaker states and
thresholds rather than writing a second backoff. Cron parsing is stdlib-only
(`jobs/cron.py`), justified by `AGENTS.md`'s lighter-option rule. `enabled`
defaults **False** (discovery is not activation, ADR-H39), and every route �
reads included � carries `require_operator` (ADR-H48), except the webhook trigger,
which authenticates on the job's SHA-256 token hash.

**Why.** The roadmap's gap #4 is "no autonomous cadence: nothing runs without a
human clicking." The existing TS loops can only refresh data; none can run an
agent, and none has a job model, run history or delivery. But they are proven and
serve a different, latency-sensitive purpose. Replacing them would be a regression
risk with no user-visible benefit. Two existing pieces already do the hard parts �
run execution/persistence and failure containment � so the phase reuses both.

**Consequences.** The three TS schedulers are byte-unchanged (acceptance gate G6).
`main.py` grows by exactly two lines (import + `include_router`) plus the lifespan
start/stop calls; all new logic lives in new modules. Save-time guardrails
(`jobs/guardrails.py`) bind a skill job to the pinned skill's manifest permissions
(refusing with the exact missing permission), require a folder for a code job,
gate `approve_external` behind an explicit operator flag, confine a watch path
with `policy.resolve_within`, and refuse an unknown delivery adapter. A missed
window is reconciled once at startup and always recorded (`missed=1`). The
delivery interface ships two adapters (`in_app` on the existing SSE bus, and
`artifact`); messaging is Phase 11, which adds an adapter without refactoring the
job model. The seven library templates ship disabled.


## ADR-H109 — Child runs are narrowed, never widened; self-reports require verifiable handles

**Decision.** Phase 7 adds bounded fan-out (`python/harness/delegation.py` + the
`delegate` tool). A child IS a normal run: it goes through the SAME graph,
registry, policy engine and persistence (`execute_run` with a `parentRunId`), and
there is NO second execution path or agent loop. The module owns only three things:

1. **The budget** — `MAX_CHILDREN=4`, `MAX_DEPTH=2`, bounded concurrency, a
   per-child timeout and a token budget. Caps are enforced at construction with
   structured codes (`DELEGATION_WIDTH_EXCEEDED`, `DELEGATION_DEPTH_EXCEEDED`,
   `DELEGATION_BUDGET_EXHAUSTED`); a writing child is refused
   (`SANDBOX_UNAVAILABLE`) when the isolation primitive is unavailable rather than
   run unisolated.
2. **The narrowing** — `child_actor(parent, child)` returns an actor whose grants
   are the parent's grants INTERSECTED with the child's scope. `operator` is NEVER
   inherited (a child did not make the operator's call, so inheriting it would
   launder authority), operator-only permissions (`skill.create/enable/...`) are
   never passed down, code verbs exist only when the parent held them, and a
   workspace wider than the parent's is refused. A requested tool outside the
   parent's allowlist is refused (`DELEGATION_TOOL_NOT_HELD`).
3. **The aggregation** — a child's PROSE is quoted; a child's CLAIM is repeated
   only with a handle the parent can re-check. A check-claim ("tests pass") is
   admitted ONLY with a `check_record_id` that verifies against the Phase 4
   verification ledger; a `run_id`/`path`/`citation` handle does not back it. An
   unbacked claim goes to `droppedClaims` and is rendered as unconfirmed — never
   silently discarded.

**Why.** The linkage already existed (`HarnessRun.parentRunId`,
`run_lineage.py`'s `RunCheckpoint`/`ToolExecutionIdempotency`, a skill's child
run), but nothing fanned out, bounded, or aggregated. Two existing precedents
made the safety model obvious: `permissions.Actor.scopes` already models a grant
set that can only narrow, and the MCP layer already holds that "a self-report is
never proof". Reusing both avoided a second narrowing implementation and a second
trust rule. The operator-non-inheritance line is the one that matters most: a
child that needs an effectful action returns the request to the parent, which asks
the operator, so authority is never laundered through a sub-run.

**Consequences.** One additive, old-row-safe `HarnessRun.delegation` column (owned
by `delegation_tools.py`, added idempotently like `run_lineage.py` owns its
columns), so the fan-out is explainable after the fact with counts only. Events
ride the existing `RunEmitter` (`delegation.started` / `child.started` /
`child.completed` / `child.failed` / `child.refused` / `aggregated`), so
`explain_run` and the session trace already cover a delegation with no new
observability surface. `delegate` is registered on the one registry and added to
both the finance and code agent allowlists. `code/tools.py` did NOT grow past its
size ceiling: the handler lives in a new `delegation_tools.py`. Writing children
get their own Phase 2 worktree; the parent lists diffs and conflicting hunks and
NEVER merges (a merge stays a Phase 5 `approve_external` action with an operator
approval). The user sees the finance job and a plain progress list, never
orchestration vocabulary.


## ADR-H110 — Computed ≠ retrieved: a code-produced number carries its code digest and never enters research claims

**Decision.** Phase 8 adds a bounded, reproducible analysis sandbox
(`python/harness/code/execution.py`, `code/recipes.py`, the `analysis_run` tool).
The sandbox runs a short program in the Phase 3 isolation primitive, records
exactly enough to re-derive the result (the VENDORED interpreter path, the source
digest, the input digests, the resolved package-set digest), and labels the output
with a `Provenance` record. The rule, enforced in code and not in a prompt:

1. Every execution output is `kind="computed"`. There is **no code path** that
   produces `retrieved` from an execution.
2. A computed number **without** a provenance record renders `UNAVAILABLE`, never
   a bare number (`render_value` fails closed: a missing record is a bug).
3. A computed number **cannot enter a research claim.** The only legal route for a
   derivation to become evidence is re-expression through
   `research/calculations.py` — an explicit act carrying formula/version/input
   provenance, never an automatic promotion. An analysis run leaves the research
   receipt untouched.
4. Imports are checked by an **AST walk** (never `eval`/`exec` on the source, never
   a regex as the only guard) against an explicit allowlist; there is no network.

The tool is **off per run** (`RunRequest.analysisEnabled`, default `False`) — the
same "discovery is not activation" discipline the MCP layer applies (ADR-H39). A
missing input is a QUESTION, not a guess: the recipes refuse with a plain prompt
rather than substituting a default or a silently shorter period.

**Why.** `research/calculations.py` is the right shape — a small, auditable,
provenance-carrying calculator — but its list is closed, so a metric outside it
ends at retrieval or nothing. Opening a sandbox without a provenance rule would
create the exact hazard `AGENTS.md` names: a plausible-looking number from
invented inputs, indistinguishable from a retrieved fact. The MCP layer already
established the precedent (every external result carries `verification`,
`eclipseVerified: false`, source and `retrievedAt` and is labelled in its text);
a computed result gets the same treatment with `computed` instead of `external`.
Point 3 is the line that keeps the phase from quietly undermining the evidence
system: without it, "run some code" becomes a laundering route into a claim.

**Consequences.** `analysis_run` registers on the ONE registry and runs through
the existing graph; the handler lives in the new `analysis_tools.py`
(`code/tools.py` stays under its size ceiling). `RunRequest.analysisEnabled` plus
`ToolContext.analysis_enabled` (default False) gate it. An additive, idempotent
`AnalysisRecord` table (owned by `analysis_tools.py`, not the ratcheted
`persistence.py`) records each run bounded. Artefacts are written to the
gitignored `.black-eclipse/artifacts/<runId>/` with a SHA-256 digest as identity,
so the behavioural reproducibility gate (same source + inputs ⇒ same digest) is
meaningful. The recipes are data, each tested and each failing honestly on a
missing input. The surface says "Worked out by Eclipse" with the method line, and
never interpreter/module/argv/exit-code vocabulary; the computed/retrieved
distinction is a front-door helper (`analysis-types.ts`) with its own invariant
test. The finance and code agent allowlists gained the tool; the finance-agent
tool-count assertion moved 24 → 26 across Phases 7–8.


## ADR-H111 — Scaffold kits are data; a generated artefact stays inert until evaluated

**Decision.** Phase 9 adds a library of eight **scaffold kits** (`python/harness/code/kits/`)
and a `scaffold_kit` tool. A kit is **data**, not a code snippet: the closed
`produces` set the repo already demands for one named artefact, typed inputs that
carry i18n prompt keys, convention statements, and a required `acceptance` rule.
The kit loader REFUSES to load a kit that has no acceptance test shipped WITH it
(`python/tests/test_kit_<id>.py`) or a declared output with no template — so a kit
cannot exist without its proof.

`scaffold_kit` renders the kit into the **task's disposable workspace** (Phase 2,
never the user's checkout), runs the kit's `checks` through the Phase 3 command
broker, and records them in the Phase 4 ledger. A failed check KEEPS the scaffold
for inspection (`CHECK_FAILED`), never silently deletes it. The rendered output is
CLOSED to the declared `produces` set; a path outside it is refused
(`OUTPUT_OUTSIDE_DECLARED_SET`). Each kit also ships a thin **draft** skill wrapper
so it is reachable through the existing `skill_invoke` path with the existing
permission model — a wrapper holds `scaffold_kit` as a required tool and no
operator permission, and can never grant anything.

The anti-fabrication generation rule (§6.5) is enforced by the templates: every
generated adapter/backtest/ingestion path returns `UNAVAILABLE` (never a default,
a synthetic series, or an extrapolation) when its data is absent, and its shipped
test exercises that branch; a generated backtest labels an in-sample metric as
in-sample and never presents it as predictive; a generated importer is idempotent
(running twice yields the same state) and its test proves it.

**Why.** The root plan's whole point is that the agent can build actual financial
software — a data adapter, a ratio, a backtest, a chart indicator, a portfolio
module, an ingestion pipeline, a research workflow, an MCP server. Each of those
shapes already has an exact convention in this repo. A kit makes the agent satisfy
that convention rather than emit plausible boilerplate: the acceptance test ships
with the artefact and fails if it is missing, and the check runs through the SAME
broker a human's change would. The inert rule is the existing ADR-025 discipline
applied to generated skills: nothing a model authored activates without evaluation
and an operator decision. Generating code without the `UNAVAILABLE` rule would
reintroduce exactly the hazard `AGENTS.md` names — a plausible-looking number from
invented inputs.

**Consequences.** Eight kits shipped (`market_data_adapter`, `mcp_server`,
`ratio_calculator`, `backtest_strategy`, `chart_indicator`, `portfolio_module`,
`data_ingestion_pipeline`, `research_workflow`), each with template(s), a manifest,
and an acceptance test under `python/tests/`. `scaffold_kit` registers on the ONE
registry and is added to both agent allowlists; its handler lives in the new
`scaffold_tools.py` so `code/tools.py` stays under its size ceiling, and
`policy.WRITE_TOOLS` includes it so the autonomy boundary removes it at
`plan_only`. Eight draft skill wrappers load (all `status: draft`, never enabled),
moving the installed-skill count 5 → 13. Kit user-facing strings are i18n keys
(`kit.*`), covered by the plain-language gate. No trading/order/broker kit ships —
an order path is a non-goal by construction. Tests: `test_kits_contract.py`,
`test_kits_scaffold.py`, `test_kits_unavailability.py`, `test_kits_skill_wrappers.py`,
and one `test_kit_<id>.py` per kit.


## ADR-H112 — Self-improvement covers code as well as skills; the policy engine and the release gate are frozen

**Decision.** Phase 10 adds `python/harness/code/evolution.py` (the recurrence
bridge, the proposal validator, the worktree evaluation, the versioning adapter and
the honest metrics), two additive tables (`EvolutionCandidate`, `EvolutionAttempt`),
and a route group. A mistake category whose RECURRENCE crosses
`RECURRENCE_THRESHOLD` becomes an **inert** candidate; a code-shaped candidate
becomes a set of structured `code/patch.py` operations; evaluation runs the target's
owning test file(s) (and any Phase-9 kit acceptance test) inside a Phase-2 worktree,
recording every execution in the Phase-4 verification ledger; activation reuses
`skills/versioning.py` **verbatim** through a thin subject adapter.

Three rules are non-negotiable and enforced in code:

1. **No unsupervised self-modification.** A candidate never activates itself;
   every `activate` route carries `require_operator` (reads included, ADR-H48) and
   records the operator decision on the candidate row.
2. **The judge cannot be edited by the judged.** A proposal touching
   `python/harness/code/policy.py`, `python/harness/skills/permissions.py`,
   `python/harness/mcp/approvals.py` or `scripts/check-all.js` is refused with
   `EvolutionRefusal(code="FROZEN_PATH")`, never silently skipped; so is any
   `policy.PROTECTED_PATHS` member (`PROTECTED`), any op that would set an
   identity/permission/tool/risk field (`FORBIDDEN_FIELD`, the `skills/patches.py`
   set as data), and any target outside the bound workspace (`OUTSIDE_WORKSPACE`).
3. **No metric without measurement.** `archive_metrics` returns the string
   `"UNKNOWN"` for any dimension it cannot derive (including `costMicros` that are
   NULL, which is why those columns are nullable) — never `0`, and there is no
   blended score anywhere; results are per source category.

**Why.** The observation side (`eclipse_memory/mistakes.py`) and the decision side
(`skills/versioning.py`) already existed; the gap was narrow — recurrence was
recorded and never consumed, and no candidate could name a source file. This phase
consumes the existing counter and drives the existing lifecycle rather than adding a
second one. The frozen set is the direct expression of README §3.3 (artifacts stay
inert) applied to the code that decides: a subject may not edit its own policy,
permissions, approvals or release gate, or "run some code" becomes a path to
authority. The nullable cost columns and the `UNKNOWN` rule exist because a report
that cannot say "I could not measure that" will say "0" instead, which is a lie.

**Consequences.** `FROZEN_PATHS` and the FORBIDDEN_FIELDS set are data;
`propose_ops` performs no model call and is the only entity that can accept an op
set (mirrors `research/claims.py`). Evaluation is deterministic — a model may
explain an outcome, never change one. The attempt archive records success, failure,
refusal and rollback alike, each with its `diffDigest`, `baseDigest` and
`evaluationJson` (including ledger execution ids), so the record is not a marketing
document. Activation maps a code subject to a thin managed skill (the change carried
in its patchable fields) so `versioning.py` is untouched, and both
`activatedVersion` and `previousVersion` survive on the candidate row. The UI is the
EXISTING learning journey (`learning_graph.py` + `learning-journey.tsx`) extended
with `evolution_candidate` / `evolution_attempt` nodes, not a second screen.
`skills/versioning.py` and `skills/patches.py` are byte-unchanged. Tests:
`test_evolution_bridge.py`, `test_evolution_persistence.py`,
`test_self_improvement_freeze.py`, `test_self_improvement_e2e.py`.

## ADR-H113 — Delivery adapters behind one interface; scope-aware surfaces; an honest sandbox backend

**Decision.** Phase 11 adds two things and changes nothing about the job model's
authority. First, delivery grows from two adapters to three behind Phase 6's
`DeliveryAdapter` protocol: `in_app`, `artifact`, and — new — `messaging`, which
carries a **template KEY plus parameters** and never composes a sentence (the
surface resolves the key through `src/lib/i18n/`, so a message that leaves the app
is translatable and visible to the jargon gate). The `artifact` adapter writes
`.black-eclipse/artifacts/<runId>/{report.md,receipt.json,meta.json}` with a path
**derived** from the server-assigned run id and confined by `policy.resolve_within`;
`receipt.json` reuses `research/receipt.py`'s shape rather than inventing a second
report format. A job may be configured with more than one destination
(`JobDelivery.targets`, additive), and each destination records its **own**
`DeliveryOutcome` on the run row — one row per target, never a rolled-up boolean. A
delivery failure is recorded and never fails the run.

Second, every new surface carries the same scope FILTER label the older routes
carry — jobs (`HarnessJob.scopeId`), code tasks (the `HarnessRun.userId` column via
`TaskStore`), artifacts (`scopeId` on `meta.json` and on the run row), and code
workspaces (`CodeWorkspace.scopeId`). The rule that must not drift, and that
`test_surface_tenancy_isolation.py` mirrors from
`test_identity_tenancy_boundary.py`: **`require_operator` stays the ONLY thing that
authorizes a mutation.** A `scopeId` in a request body is a filter label; it can
narrow what is returned and can never widen what is permitted.

Third, the command broker gains a documented `SandboxBackend` interface
(`python/harness/code/backends.py`) with three declarations — `local` (the
zero-config default, `code/sandbox.py` itself, behaviour unchanged), `container` and
`remote`. Each backend declares its `guarantees` (filesystem, network, resources,
wall clock, process tree, environment, output cap). The honest-failure rule is
absolute: an unavailable backend refuses with `SANDBOX_UNAVAILABLE`; it never
degrades to `local` and never to an uncontained run. The `local` declaration is
built FROM the enforced policy constants, so an upgrade cannot restate a weaker
guarantee as a stronger one.

**Why.** The delivery interface existed and had almost nothing behind it: a job
that ran at 07:30 produced a good report and could only land where the app could
put it, while the user had asked for a message. The scope labels existed on the
older routes as filters, but the newer surfaces (jobs, code tasks, artifacts,
workspaces) did not carry them — so "not multi-user safe" risked quietly becoming
"not even scope-aware", which is worse. And the broker was welded to the local OS
with nothing documenting what a *different* backend would have to guarantee, so
nobody could add one without guessing. This phase closes those three gaps
additively: it adds adapters and a backend interface; it does not refactor the job
model (README 3.1). The message body is the highest-risk surface in the whole
roadmap — it leaves the app and lands in a person's inbox — so it gets the strictest
reading: a template carries the finance job's name and a count, and nothing else
the user did not choose to receive; no run id, job id, duration in ms or delivery
code ever appears.

**Consequences.** `jobs/model.py` grew only additively (`JobDeliveryTarget`, an
optional `destination`/`targets` on `JobDelivery`, an optional `scopeId` on
`JobDefinition`); a job saved before this phase still delivers exactly as it did,
yielding a single derived target. `jobs/store.py` records `deliveryJson` as a LIST
of per-target outcomes and normalizes an older single-dict row to a one-element
list without rewriting it. A new route `GET /jobs/{id}/runs/{runId}/artifact` reads
a saved report and refuses a read from a different scope (404). `scripts/doctor.js`
probes vendored Python, the artifact directory, the container backend and the remote
backend; it repairs only what is safe to repair (it never installs a container
runtime), reports a missing optional backend as "not available" while the run
continues, and exits non-zero only when the vendored interpreter the runtime
genuinely requires is missing. `deployment_exposure`/`identity_boundary` are
unchanged and the app still claims no multi-user safety. Tests:
`test_delivery_adapters.py`, `test_surface_tenancy_isolation.py`,
`test_sandbox_backends.py`, plus the extended plain-language gates and the three
runbooks (`runbook-add-a-job.md`, `runbook-add-a-kit.md`,
`runbook-failed-code-task.md`).

## ADR-H114 — The code eval gate is part of the one honest release gate

**Decision.** Phase 12 extends `python/harness/code/eval/` with a **task + safety**
evaluation beside the Phase-4 verification eval, and adds it to the repo's single
honest release gate by extending `scripts/test-evals.js` (which `scripts/check-all.js`
already runs — the frozen gate file gains no step). The addition is:

1. `dataset_tasks_v1.json` — seven labelled fixtures by difficulty (one-file,
   cross-file, test-first, failing-check repair, kit scaffold, job definition, and a
   **refusal** case), each with its gold outcome, owning checks and rationale.
2. `safety_cases.py` — eleven adversarial cases as DATA, one test each in
   `python/tests/test_code_eval_safety.py`. Every test asserts **both** halves: the
   attack was blocked or contained, AND the refusal was recorded with its structured
   code. A block with no record is a failure.
3. `tasks.py` / `safety.py` / `statement.py` — the deterministic runners and the
   capability-statement generator.
4. `check_task_thresholds` — a deterministic floor, never a blended score:
   `falseVerifiedRate == 0.0`, `refusalCorrectness == 1.0`,
   `refusalRecordedRate == 1.0`, `kitAcceptanceRate == 1.0`, and an exact dataset
   checksum. `taskSuccessRate` is measured and printed, deliberately NOT a 1.0 gate.
5. `docs/harness/capability-statement.md` — the per-shape "can Eclipse build X
   today" table, **generated** from the dataset and the report (a byte-compare test
   proves it cannot drift). A shape with no fixture reads `not measured yet`, which
   is a different claim from `not yet`.

The refusal fixture is graded in the OPPOSITE direction to every other: producing a
plausible answer is the FAILURE; declining with the structured code is the PASS.

**Why.** Three gaps were concrete. The code capability had no labelled task set —
"can Eclipse build X?" was answered by prose. The safety properties were asserted in
prose and attacked by nothing, so a property nobody attacks is a property nobody
knows is still true. And the release gate did not run a code-capability eval, so a
regression in the measurement was invisible. The failure mode this phase exists to
prevent is **a gate that always passes**; that is why one gate is not "does the eval
pass" but "does a deliberately injected regression make it fail". The report is per
category, never one score, because one number hides the slice that always fails
behind the one that always succeeds, and an unmeasurable dimension prints `UNKNOWN`
rather than a fabricated `0`. The capability statement copies the exact honesty
discipline `src/lib/harness/capability.ts` already applies per market: it declines to
advertise a guarantee it cannot name.

**Consequences.** `scripts/check-all.js` and the frozen three are byte-unchanged;
the new step lives inside `test-evals.js` beside the existing floors. The Phase-4
verification eval keeps its name and API — this phase ADDS a distinct `code gate`
(the task + safety eval) rather than redefining it, so both gates print and both
pass. The eleven safety cases are data, so a new attack is a new row and a new
parameterised test, never a rewrite. The capability statement's every cell is a
`capability.*` i18n key, so the plain-language gate reads every word a finance user
sees; the eval report itself stays engineering-facing and is never rendered to a
user. The injected-regression proof asserts the **failure** of the gate (the failing
run is the evidence) and then reverts. Tests: `test_code_eval.py`,
`test_code_eval_safety.py`, plus the extended plain-language gates.
