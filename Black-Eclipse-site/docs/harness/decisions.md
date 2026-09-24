---
title: Harness Decisions
status: Current
last-verified: 2026-09-24
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
automatically after the run (`auto_candidate_detection` default **on**): the
deterministic, criteria-driven analyzer creates inert learning candidates
without the user asking, and the run's `memory` blob reports
`learningEligibility.autoCaptured` + `learningAnalysis.candidatesCreated` for the
UI. Candidates are deduplicated by signature (bounded queue) and are NEVER
enabled/promoted. The explicit "Learn from this run" action remains for cases
auto-detection does not cover (e.g. an explicit turn-into-skill request on a run
with no tool trace), and an explicit request always yields an inert candidate.
Candidate → draft generation produces a complete `SKILL.md` (procedure steps,
typed input/output assumptions, existing safe tools only, source-run provenance,
limitations, evaluation cases) while remaining `status: draft` /
`evaluationStatus: not_evaluated`. When the trace has no evidence for a real
procedure, the draft says so and stays a manual-authoring candidate.

**Why.** Drafts were manifest-only (`instructions: None`), so "turn this into a
skill" produced an unusable artifact; ordinary chat runs could not become
learning candidates; and requiring the user to manually trigger learning meant
successful work routinely never became a candidate.

**Consequences.** No automatic skill enablement/promotion/permission expansion —
the hard rule is preserved (the policy `auto_promote_low_risk` stays locked
off). Automatic learning at most creates inert records; a draft is stored as an
inert version and only evaluation + operator approval can enable it. Operators
can disable detection entirely via `auto_candidate_detection=false`.

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
- `run_only` — relevant to this task/conversation only;
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
detection and automatic suggestions all default **off**; turning them on is an
explicit operator choice that still only produces inert records.

**Why.** The Phase 3-M reliability pass made capture deterministic but too eager:
`auto_capture_enabled`/`auto_candidate_detection` defaulted on, an incidental "I
prefer …" or "Always use X" classified as an explicit save, and the `memory` tool
wrote straight to the service pipeline with no check against the user's actual
words. The result was a database that filled with incidental, task-specific and
occasionally financial text — exactly what a durable memory must not contain.

**Consequences.** One code path authorizes every write, so a new surface cannot
quietly bypass the rules. Explicit controls stay dependable; everything else is
selective and usually `run_only`/`ignore`. A persisted unsafe `true` policy
override is migrated to the safe default (migration 5, recorded in
`MemoryPolicyMigration`) rather than silently continuing the old behaviour. The
storage budget (`max_memories`, default unlimited) fails a new unique save
truthfully as `memory_full` rather than auto-deleting user memory; inert history
does not consume it. The learning path is distinct: a skill candidate is an
on-demand procedure created only through an explicit "turn this into a skill"
request or the operator's "Learn from this run" action (automatic detection
opt-in), never a second memory note.

## ADR-H7 — Zero-config is preserved via automatic provisioning
**Decision.** `postinstall` and `doctor.js` install the Python agent stack
automatically; the runtime is spawned on demand. If Python is genuinely
unavailable, runs fail with a clear 503.

**Why.** `npm install && npm run dev` must keep working for open-source users,
now that the agentic runtime is Python.

**Consequences.** First run may take longer while pip installs. `npm test` runs
both the Vitest and pytest suites; the Python suite is skipped (not failed) when
the stack is absent.
