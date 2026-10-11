---
title: Harness Decisions
status: Current
last-verified: 2026-10-07
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


## ADR-H115 — A source is never the authority; agreement between sources is arbitrated

**Decision.** Phase 13 replaces the two static orderings that decided a
price-shaped answer (`planner._PLAN` and `layer._SINGLE_BEST`) with ONE authority
in `python/harness/retrieval/authority.py`: `AUTHORITY`, one `DataTypeAuthority`
row per data type holding the ordered candidate list, whether the type is
`single_best` (first success) or `arbitrated`, and the freshness ceiling for the
type; and `decide_source`, a pure function that returns the chosen source, a plain
reason, and every rejected candidate with why. `current_quote`,
`historical_prices`, `macro_series` and `company_profile` become **arbitrated**:
every eligible candidate runs (through the existing `parallel.run_parallel` seam),
and the existing `conflicts.detect_conflicts` / `layer._resolve` chooses the
highest-tier newest value (`sources agree`) or reports `CONFLICTING` with every
candidate and its provenance. No second conflict mechanism is introduced. A
candidate whose newest observation is older than
`min(authority.request_window_s, request freshness window)` is ineligible to
answer and is rejected with `STALE_SOURCE` and the measured age; when every
candidate is stale the status is `NO_FRESH_SOURCE` (distinct from `UNAVAILABLE`,
which means none answered at all). `financial_statements` and the qualitative
types stay `single_best` — an issuer filing is not a race with a snapshot.

**Why.** The vault was first for every price-shaped type and `_execute_single`
returned on the first success, so the live provider was **never called** once the
vault answered. A vault-vs-live disagreement could not occur, which made the
0.5 % conflict tolerance — written for exactly that case — unreachable. The system
prompt already stated the correct rule ("the vault is one source, not the
authority"); the code contradicted it. A prompt cannot fix a source that is never
consulted; only arbitration can. This is a correctness fix, not new power: nothing
new becomes writable, and no new data source is added.

**Consequences.** `planner._PLAN` and `layer._SINGLE_BEST` are deleted and their
readers repointed, so there is one ordering in the tree, not three. The web route
stays forbidden for the precise types (`historical_prices`, `macro_series`,
`derived_metric`). A `realtime` price request can no longer be satisfied by a
22-day-old vault row, and the refusal names the age. A cross-source disagreement
is `CONFLICTING` with both candidates — proven by a test that fails on the
pre-change code. Tests: `test_source_authority.py`, the retrieval regression
suites, plus the plain-language gates.

**Amendment (follow-up).** The arbitration only governs calls that go through the
retrieval layer. The agent also held `get_market_snapshot` (`finance_tools.py`),
which read the vault price/market-cap directly and **never ran the layer at all** —
so a months-old market cap could still be presented as current (the reported
demo). `get_market_snapshot` now routes its price/change/market-cap leg through the
same arbitrated `current_quote` path: a fresh live reading beats the saved
snapshot, a stale snapshot is not asserted as current, the observation time and its
age are stated, and a disagreement beyond the tolerance shows every contested
figure rather than the stored one. `normalize_quote` dates a live payload from its
`observationTime` so the cross-source grouping can see it. This confirms the ADR's
own rule at the tool grain: a source is never the authority, whichever entry point
the model chooses. Tests:
`test_demo_stale_market_cap_is_not_returned_as_current`,
`test_demo_disagreement_is_shown_when_sources_differ`.

## ADR-H116 — An observation's age is a property of the observation, not of the payload

**Decision.** `NormalizedFinancialObject` gains two ADDITIVE fields,
`observation_time` (the market time the value is about) and `observation_source`
(`provider_asof` | `snapshot_write` | `unknown`, defaulting to `unknown`), so an
old payload still loads unchanged and a missing time is never fabricated.
`validate.py` gains `validate_observations` beside the existing dataset-level
`validate_objects`: it stamps an individual stale row `warning` and reports it,
and a value whose only time is a snapshot write gains the transformation
`saved snapshot, not a live reading` and is `warning` for a `realtime` request —
never worded as live. The check is applied to non-series payloads only (an old
bar inside a history series is the point of history, not a defect).
`src/lib/harness/data-bridge.ts` supplies the fields additively:
`marketSnapshot` returns `observationSource: "snapshot_write"` with the vault
row's write time, and `liveQuote` returns `"provider_asof"` only when the provider
reports its own market time and `"unknown"` otherwise — the retrieval clock is
never dressed up as a market as-of. `cadenceSeconds` stays, but as a hint: the
runtime decides eligibility.

**Why.** The dataset-level check (`_newest_timestamp`) answers "is this batch
current?" — a payload of 40 rows where 3 are a month old passes it, so a stale row
could ride a fresh batch silently. An observation's age is a fact about that
observation. Separately, the vault's schema has no market-as-of column, so its
only timestamp is the snapshot write time; a value whose age is unknown must say
so rather than imply it is live. This is the honesty rule (`never fabricate`) at
the per-value grain.

**Consequences.** Older payloads load with `observation_source == "unknown"` and
are unaffected until a source starts reporting a time. The user-facing strings for
the as-of / delayed / disagreement wording are i18n keys (`source.*` in
`src/lib/i18n/dictionaries/en.ts`), so they pass the plain-language gate and name
the number, not the plumbing ("This is a saved reading, not a live price"). Tests:
`test_source_authority.py` (per-observation staleness), plus the extended
plain-language gates.

**Amendment (follow-up 2).** "An observation's age is a property of the
observation" must hold as **per-field** provenance, not per-payload. Routing
`get_market_snapshot` through the layer was not enough: the live provider for US
equities (yfinance `fast_info`) returns a price and **no market cap**, so the cap
always fell back to JDdS while the payload was labelled "verified" — the original
demo defect wearing a verified badge. The cap is now actually carried from the
provider when it exists (`scripts/yfinance_bridge.py` → `fetchers/yfinance.ts` →
`data-bridge.ts`), and when a single field falls back to the stored snapshot it is
labelled `— saved snapshot` with its stored time and source; the top-level
`verified` flag is true only when the PRICE itself is live, and each field's origin
rides on the structured payload. A value can never borrow another value's
provenance. Tests:
`test_demo_live_price_but_no_live_cap_labels_the_cap_saved` (the real US-equity
shape), `test_demo_stale_market_cap_is_not_returned_as_current`.

**Amendment (follow-up 3 — the general rule).** Verification is not a property of
the price leg; it is a property of every data type. Two capabilities were still
vault-bound and would fail or go stale for anything the committed snapshot lacks:
`fundamentals` (the company profile) and `market_snapshot` (a symbol absent from
the universe, or a vault row with no stored price). The vault is a **cache, not a
precondition** — the rule `financial_statements` already followed is now applied
uniformly. `fundamentals` enriches from the existing live provider pipeline
(SEC → FMP → Yahoo) when the vault lacks the profile, and reports which answered
(`profileSource`); `resolveAnyInstrument` recovers a `not_found` for a KNOWN,
covered market so a live quote can serve an instrument the vault never stored.
This is not a bypass: the identity gate still refuses AMBIGUOUS, `not_covered` and
wrong-currency answers, so a live provider can never price the wrong instrument.
The live yfinance bridge now carries `marketCap` too. Tests:
`data-bridge.test.ts`, `data-bridge-phase2.test.ts`, `data-bridge-health.test.ts`.

## ADR-H117 � One way in: the code capability is reached from the conversation, not a second form

**Decision.** A coding request typed in ordinary chat is served by the code
capability that already exists, through three additive pieces. (1)
`python/harness/code/request_intent.py::classify_code_request` � a deterministic,
model-free classifier returning `code_change` | `code_question` | `not_code`,
where an AMBIGUOUS turn is `not_code` (the refusal path is the safe failure). It
is reached over the read-only, operator-gated `POST /code/intent`. (2)
`python/harness/agents.py::CHAT_CODE_TOOLS` � a NARROWED profile applied per turn
inside the existing `graph.resolve_surface`, after the autonomy narrowing, so
there is ONE place a run's profile is computed. `code_change` ? `edit_verify`
(write + execute + verify), `code_question` ? `plan_only` (read-only). The four
external actions (`code_commit`/`code_push`/`code_open_pr`/`code_deploy`) are
absent from the declared set and can never be added back by a profile. (3) The
front door learns to send `autonomy` (`plan_only` | `edit_verify` only,
fail-closed on any other value) and `analysisEnabled`; `startChatRun` resolves
them from the classifier. The runtime's registered tool set is UNCHANGED � the
phase changes an allowlist and a payload, never a tool.

**Why.** The modules existed and were registered on the one registry, but
`eclipse-agent`'s allowlist could not read a file, apply a change or run a
command; the front door never sent an autonomy, so `plan_only` was the only
profile anyone reached and `analysis_run` was unreachable from the product. A
capability that is unreachable is, from the user's seat, missing. The classifier
is deterministic code, not a model call, because a model's opinion cannot grant a
capability (README �3.1, �3.2). External actions stay on the Code Tasks surface
where the single-use approval panel lives, so chat cannot commit, push, open a
review request or deploy.

**Consequences.** A `code_change` turn binds `workspace_patch_apply` and
`command_run` (proven against the BOUND schemas, not the prompt); a finance turn
binds no change/execute tool and behaves exactly as before. A refusal is honest
and specific (`PROFILE_DENIED`, `WORKSPACE_UNBOUND`, `SANDBOX_UNAVAILABLE`,
`COMMAND_NOT_ALLOWLISTED` carry existing plain sentences). `analysis_run` is on
only for a turn that already asked for a code change; Phase 15 owns the richer
quantitative classifier. User-facing copy lives under `code.chat.*` and passes
the plain-language gate. `RunResult.capability` is a first-class field: the
profile rides inside the existing `codeVerification` blob (`autonomy`/`workspaceId`)
and `code/capability.py::capability_from_verification` derives
`{kind, profile, headline, verification}` (an i18n headline KEY, never a
category); the panel prefers it and falls back to the flat fields for older rows.
A "Build this" / "Schedule" action on the code task list reuses the EXISTING
`/api/code/tasks` and `/api/jobs` contracts; a scheduled code job is created
disabled (`agent_id="code-agent"`, `autonomy="edit_verify"`).
Tests: `test_code_request_intent.py`, `test_chat_code_profile.py`,
`test_code_reachability.py`, `chat-capability-panel.test.ts`.

## ADR-H118 — The folder a person chooses is a trusted root; approval is the one widening act

**Decision.** OpenCode-style general software work is enabled without repealing
the isolation invariant. A person picks a folder; an operator approves it
(`POST /workspace/roots`, `require_operator`); it is persisted in a
`TrustedRoot` table on the runtime's own `agent-memory.db`. The SELECTED root is
what `workspace.default_root()` resolves to, after the `BLACK_ECLIPSE_CODE_ROOT`
override and before the built-in repo root, so zero-config is unchanged and a
chosen folder takes effect on the next run without a restart. Approval is the
ONE place a new root becomes workable; every read and write is still confined by
`policy.resolve_within`, and `PROTECTED_PATHS` remain untouchable inside an
approved folder.

**Why.** The prior design bound only the server's own repo root, so a person
could never point Eclipse at their own project. Widening "any path the model
names" would be a security hole; a persisted, operator-approved allowlist is the
narrow, auditable widening that keeps the model from choosing its own boundary.

**Consequences.** `code/roots.py` owns the registry + a bounded directory
browse. `routers/workspace.py` owns the routes. The editor's file APIs
(`/workspace/files`, `/workspace/file/read|write`) use the SAME confinement the
agent tools use, so the human editor is a second door to one boundary, never a
weaker one. A root that vanishes falls back to the repo root rather than failing
every run.

## ADR-H119 — A direct edit is opt-in and lands in the real folder; the sandbox stays the default

**Decision.** `worktree.allocate(direct=True)` returns the resolved root itself
(strategy `"direct"`) instead of a disposable worktree or snapshot; `release`
NEVER deletes a direct workspace. Direct mode is reachable only for a run whose
root resolution already succeeded, and a code task defaults to direct when (and
only when) a trusted folder is selected — an explicit `direct` always wins. The
built-in repo root with no selection stays isolated.

**Why.** "Pick a folder and edit it" is the point of choosing it; making the user
flip a second switch after the explicit folder approval would be ceremony. The
safety comes from the approval (ADR-H118) and the confinement (unchanged), not
from a copy. The copy remains for the built-in repo, where the operator never
opted in.

**Consequences.** `RunRequest.direct` is additive and default-False at the
schema level (old callers unchanged); the route resolves the default from the
selected root. `worktree.diff` reports a direct workspace honestly: a git diff
when the folder is a checkout, an empty result otherwise — never a synthesized
change.

## ADR-H120 — The terminal is one tool with a three-way classifier, not a shell

**Decision.** `terminal_run` runs an arbitrary command WITHOUT a shell
(`shlex.split`, argv exec through `code/sandbox.py`). A pure classifier sorts
every command into `allow` (a safe-program allowlist: interpreters, package
managers, test/build/lint, git, read-only coreutils, safe file mutators), `ask`
(anything else), or `deny` (destructive shapes, shells, downloaders, and
shell-chaining metacharacters). `allow` runs; `ask` requires a single-use,
workspace-bound approval (`kind="terminal_command"`) created on first call and
consumed on retry; `deny` is refused and is never approvable. The registry's
effect authorizer and the handler both enforce the verdict.

**Why.** The user asked for real terminal access. The safe way to add it is not
to delete the closed command table but to add a generic tool whose safety is a
classifier enforced in Python — never by a prompt — plus the existing
sandbox/wall-clock/output/process-tree bounds. No shell means a `; rm -rf` is
inert text, not a second command.

**Consequences.** `code/terminal.py` owns classification + `RunSpec`; the
handler is `code/terminal_tools.py`; the tool is registered only on the
code/chat surfaces and is removed at `plan_only`. Every execution is recorded in
`HarnessCommandExecution` and the verification ledger exactly like `command_run`,
so a claim about it is checkable.

## ADR-H121 — The live stream shows what a tool is doing, content-free

**Decision.** `tool.requested` carries a bounded `detail` and `tool.completed`
carries a bounded `summary`, both derived by one pure function
(`code/activity.py::tool_detail`/`tool_result_summary`). A `detail` is a command,
a file PATH, or the changed PATHS; a `summary` is an exit code, a count, or
"timed out". File CONTENT is never included: a `workspace_patch_apply` carrying a
secret in `content`/`new` summarizes to its paths alone.

**Why.** A coding harness earns trust by showing its work — "Running
`python app.py` → exit 0", "Writing the change `stream.py` → 1 file(s)". Eclipse's
chat showed only a tool NAME ("Reading a file"), so the surface read like a
chatbot with a spinner, not a harness. The fix belongs at the emitter: the
runtime owns the tool call and its data, so it can summarize safely.

**Consequences.** `activity.py` owns the derivation (a fixed field allowlist per
tool; a `MAX_DETAIL_CHARS` bound). The event carries display metadata only — it
is never an authorization. `ActivityItem.detail` is the one new client field; the
activity reducer already spreads it through. A tool with no safe detail or a
result with no known shape reports nothing rather than a fabricated line.

## ADR-H122 — Replanning is one bounded node on the existing graph, flag-gated and default off

**Decision.** When a tool step FAILS (one or more tool errors) or STALLS (the
agent issues the same `(tool,args)` set as the immediately preceding turn), the
loop may divert through ONE `replan` node before returning to the agent. The node
appends INERT prose naming what failed or stalled; it authorizes nothing, widens
no allowlist, and builds no second graph, registry or model adapter. The path is
FLAG-GATED (`HARNESS_REPLAN_ENABLED`) and DEFAULT OFF; bounded by
`ReplanBudget.max_replans` (default 2); observable via a persisted `run.replanned`
event (`replan`, `reason`, `maxReplans`). The trigger predicate, budget and
directive live in `python/harness/replan.py`; the node sits on the SAME
`tools → agent` edge in `graph.py`. A stall outranks a failure when both hold.

**Why.** A long tool loop can repeat itself until `maxSteps` and answer nothing —
`MAX_STEPS_EXCEEDED` is the honest failure but a poor outcome when a revised
approach was available. The fix must not become the thing the platform forbids
(ADR-H1): no second agent loop, tool registry or model adapter, and no privilege
created by a replan. An explicit, bounded, observable revision step satisfies the
capability without crossing those boundaries.

**Consequences.** `graph.py` gains a `replan` node only when the flag is on (the
edge mapping is built conditionally, so a disabled run's graph is byte-identical
to before). `GraphState` gains bounded replan fields (`replans`, `step_failures`,
`stalled`, `last_turn_keys`, `step_failure_details`). To stay under the file-size
ratchet, the checkpoint (de)serialization moved to `checkpoint_io.py` and the
history-bounding + dropped-context helpers moved to `history.py` (both
re-exported by `graph.py`, so callers/tests are unchanged). An optional,
best-effort model-authored plan (`replan.model_replan`) is additive and can only
be text; the deterministic directive is the fallback. Tests:
`python/tests/test_replan.py`.

## ADR-H123 — The model layer is a provider-agnostic runtime, not a per-run factory

**Decision.** Eclipse gains a `ModelRuntime` layer (`python/harness/model_runtime/`)
that is the ONLY interface the rest of Eclipse uses to reach a model:

    Agent → ModelRuntime → ModelRouter → ProviderAdapter → Provider

`build_chat_model` is demoted from "the model seam" to a low-level construction
primitive that provider adapters delegate to; no agent, tool, memory or financial
logic names a provider. The runtime owns: a provider registry and a model
registry seeded from the existing `PROVIDER_CATALOG`; capability detection as
states (`supported` / `unsupported` / `unknown` / `degraded`); task profiles;
logical aliases resolved dynamically; a scoring router (capability, quality,
reliability, latency, availability, context, cost) with configurable weights;
fallback and error-aware retry with exponential backoff + jitter; health, circuit
breaker and rate-limit managers; normalized token/cost/latency/budget tracking;
normalized streaming, tool schemas, structured output and reasoning; and an
explainable routing decision trace. Persistence lives in the runtime's OWN
`ModelRequest` / `ModelHealth` tables on `agent-memory.db` — never JDdS (spec §37).

**Why.** The agent was hard-wired to one resolved provider per run with no
health, fallback, cost or capability awareness, so "switch model" meant editing
the graph. A financial platform must let the model change without changing what
the data means: model selection must be observable, cost measurable, failures
recoverable and capabilities explicit, while the Evidence engine stays the sole
source of financial truth. Reusing `PROVIDER_CATALOG` and `build_chat_model` keeps
one source of provider facts and one construction path rather than a second copy.

**Consequences.** `graph.py` resolves and builds through the runtime but still
invokes the module-level factory, so the existing test seam (dozens of
`monkeypatch.setattr(graph_module, "build_chat_model", …)`) and all 2535 harness
tests are unchanged. A concrete provider/model in `ModelSettings` stays the
explicit override (spec §44); the router only changes it when it can build with
the run's credentials (same provider) or a keyless local provider, so it never
silently routes to a paid provider the operator did not configure (spec §31/§45).
Cross-provider fallback and in-place retry are flag-gated
(`HARNESS_MODEL_FALLBACK` default OFF, `HARNESS_MODEL_RETRIES` default 1) so
single-credential zero-config behaviour is byte-identical. Model usage/health
persist to `agent-memory.db` via `model_runtime/store.py`; read-only inspection
routes (`/model-runtime/*`) are operator-gated. Tests:
`python/tests/test_model_runtime.py`.



## ADR-H126 — The terminal is infrastructure with one runtime shared by the agent and the UI

**Status:** Accepted (2026-10-05)

**Context.** Eclipse already had three execution paths that had grown
independently: `code/sandbox.py` (bounded one-shot argv execution),
`code/shell.py` (a shell string, background `spawn`), and `code/terminal.py` /
`terminal_tools.py` (a classified, shell-free command). Each was correct in
isolation, but none owned a *process*: a background `npm run dev` returned a pid
the agent polled by hand, there was no persistent shell that preserved `cd` and
environment, no port detection, no process tree, no crash record, no recovery
after a restart, and the visible terminal panel was a second, weaker execution
door with its own state in React. The request is broader: give Eclipse the
execution backbone of a serious agentic harness, with one runtime underneath both
the agent tools and the UI.

**Decision.** Add `python/harness/terminal/` as infrastructure, not a UI feature:

1. **One facade.** `TerminalManager` is the only terminal entry point; the agent
   tools (`terminal/tools.py`) and the HTTP router (`routers/terminal.py`) are thin
   adapters over it, so UI and agent can never disagree about process state.
   React state is never the source of truth.
2. **Two primitives + a session.** `execute_command` (bounded, cancellable,
   through `code/sandbox.py`), `start_process` (a monitored long-running process
   with no ordinary timeout), and `open_shell`/`run_shell_command` (a persistent
   shell preserving `cd`/environment). A real PTY is used when a PTY library is
   installed; the piped fallback is reported as `pty: false`, never called a PTY.
3. **Deterministic process state.** A state machine applied once by the monitor
   thread that reaps the OS exit — never inferred from "does a PID exist". stdout
   and stderr are separate, sequenced ring buffers with a cursor, so polling never
   duplicates output and large output is bounded.
4. **Honest runtimes.** `LocalRuntime` and `WSLruntime` are implemented;
   `DockerRuntime` and `SSHRuntime` exist and refuse with `NOT_IMPLEMENTED`.
   `select_runtime` never degrades to local.
5. **Reused safety.** The tools are removed at `plan_only` through the existing
   `code/policy.allowed_tools`; the classifier is the existing
   `code/shell_tools._verdict`; approvals are the existing single-use store;
   redaction is the existing `session_index.redact_span`; persistence is the
   existing one `agent-memory.db` connection, owning only its own tables.
6. **Recovery.** On boot, a persisted process whose pid is gone is `EXITED`; one
   whose pid still exists is `UNKNOWN`, never `RUNNING`. Sessions are closed.

**Why.** A coding/agentic harness is only as capable as its execution layer: the
loop *modify file → run → read error → fix → restart → verify* cannot exist
without persistent processes, streamed output, ports and crash detection. Doing
this inside the existing sandbox would have conflated one-shot bounded execution
with long-lived process management; doing it in TypeScript would have violated
the "agentic runtime is Python" rule; doing it as a UI feature would have made the
terminal unusable headless, which is exactly when autonomous agents need it. One
shared runtime keeps the agent and the human looking at the same truth.

**Consequences.** `code/sandbox.py`, `code/shell.py`, `code/terminal*.py`,
`code/backends.py`, `code/policy.py`'s command vocabulary and every existing test
are preserved; `terminal_run`/`shell_run`/`shell_spawn` remain for compatibility
and share the classifier. `policy.py` gains `TERMINAL_WRITE_TOOLS` /
`TERMINAL_READ_TOOLS` and `SECRET_ENV_ALLOWLIST` gains `PATHEXT` (a measured
latent gap: a scrubbed shell could not resolve an executable by name). Both agents
and `CHAT_CODE_TOOLS` gain the terminal tools; the pinned chat-set test is updated
in place. New tables are additive on `agent-memory.db`. Tests:
`python/tests/test_terminal_{buffer,shell_and_runtimes,process,session,store_and_recovery,tools,api,e2e}.py`.
Full suite green; `npx tsc --noEmit` clean.


## ADR-H127 — Real PTY by default; Docker/SSH runtimes; runaway is reported, never auto-killed

**Status:** Accepted (2026-10-05)

**Context.** ADR-H126 shipped the terminal subsystem with four explicit
limitations: a piped fallback when no PTY library was installed, Docker/SSH
runtimes that only declared an interface, and no resource telemetry or
runaway-process policy. A coding harness that cannot render a real interactive
prompt, run a build inside the project's container, or notice a spinning process
is missing the things its execution loop is most often pointed at.

**Decision.**

1. **Real PTY is the default.** `pywinpty` (Windows) / `ptyprocess` (POSIX) are
   declared in `python/requirements.txt` behind platform markers, so the default
   install yields a genuine ConPTY/forkpty (`pty: true`). The agent-facing session
   text has ANSI stripped; the UI reads the raw buffer so a real terminal can
   render. A `cd`/`export` is sent to the REAL shell, the resulting cwd is read
   from the shell's own prompt via the sentinel, then confined to the workspace; a
   command that leaves the root is refused and the shell returned to the root. The
   piped fallback remains, and stays honestly reported as `pty: false`.
2. **Docker and SSH are implemented** for command execution and background
   processes, behind operator config (`HARNESS_TERMINAL_DOCKER_CONTAINER`/`_WORKDIR`,
   `HARNESS_TERMINAL_SSH_HOST`). Interactive sessions for them refuse
   `NOT_IMPLEMENTED` (a session needs a shell we drive directly). SSH uses the
   host's own OpenSSH config/agent with `BatchMode=yes`; the subsystem never reads,
   stores or forwards a key or password. A new `extra_env()` lets a runtime forward
   only the non-secret host variables its client needs (`DOCKER_HOST`,
   `SSH_AUTH_SOCK`), merged over the scrubbed base environment.
3. **Runaway is reported, never auto-killed.** `resources.py` reads CPU/memory
   directly from the OS (no `psutil`). `ResourceLimits` refuses a start past
   `maxProcesses` with `PROCESS_LIMIT`, and flags — but never kills — a process
   whose output buffer or lifetime exceeds its bound, emitting
   `terminal.process.runaway`. A legitimate long-running dev server is exactly the
   case this must not mistake for a fault.

**Why.** The alternative — keeping the four limitations — would leave the harness
unable to do the interactive work it exists for, and the alternative to (3), an
auto-kill, would destroy a user's server on a heuristic. The honest middle is:
real capability by default where the platform supports it, operator configuration
for the remote surfaces, and a report-and-let-the-operator-decide rule for a
possible runaway.

**Consequences.** `requirements.txt` gains two optional-but-default deps (with
markers, so neither is installed needlessly). `runtimes.py` grows past its prior
stub; `shell_detect.capabilities()` now lists a runtime only when it can actually
serve a command. `policy.SECRET_ENV_ALLOWLIST` is unchanged — runtime-specific vars
come from `extra_env()` per call, not the global allowlist. Tests:
`test_terminal_resources.py`, the Docker/SSH unit cases, and real-PTY session
coverage. Full Python suite green (2636); Vitest 2093; tsc clean; eval gates PASS.

## ADR-H128 — Code intelligence is one engine over LSP/AST/index, never a set of LSP wrappers

**Status:** Accepted (2026-10-06)

**Context.** Eclipse could read, search and patch files, but it treated the
repository as text: there was no definition/reference lookup, no dependency or call
graph, no diagnostics loop, and no way to give the model a focused slice of code
instead of a directory dump. Competing coding agents understand software
structurally and semantically. The task: build a first-class Code Intelligence &
Understanding Engine (CIUE) that is NOT a few LSP wrappers, is transport-agnostic,
degrades honestly, and reuses the existing filesystem/terminal/tool/policy
infrastructure.

**Decision.**

1. **One facade over four backends.** `CodeIntelligenceManager`
   (`python/harness/code/intel/`) coordinates an LSP manager, a Tree-sitter layer,
   an AST engine and a dedicated local index, and normalizes every answer into a
   Unified Code Model (`models.py`). The agent asks `code_get_definition` /
   `code_find_references` / `code_find_symbol` / … and never learns which backend
   answered — but every result NAMES its engine (`lsp` / `tree-sitter` / `ast` /
   `index`). LSP is tried first, then the structural fallback; a server failure
   never crashes the runtime.
2. **Provider registry, not a hard-coded server.** `lsp/providers.py` ships nine
   real servers (TS/JS, Python, Java, C#, C/C++, Go, Rust, PHP, SQL); adding one is
   adding a `LanguageServerSpec`. Providers are probed, never assumed.
3. **A DEDICATED index.** `persistence/index.py` (`CodeIndex`) is its own SQLite
   store under `.black-eclipse/code-index/` — never `agent-memory.db`,
   `eclipse-memory.db` or `jdds.db`. It is incremental (changed files only), a cache
   (every query can fall back to a live scan), and recoverable (a corrupt database
   is backed up, recreated and re-indexed).
4. **Reuse, not rebuild.** Path safety is `code/policy.py` + `code/workspace.py`;
   reading/encoding/watching and the per-language extractors are `code/fs/`; the
   tool registry, event emitter and effect authorizer are the existing seams. No
   second confinement implementation, filesystem, terminal or registry.
5. **Rename is semantic or it is a labelled preview.** LSP `WorkspaceEdit` when a
   server runs; otherwise a deterministic, preview-first structural edit from the
   index. Never a regex. Applying requires `code.write` (removed at `plan_only`) and
   writes through the fs atomic encoder.
6. **Deterministic context first.** `context.py` selects relevant files, symbols,
   call paths, diagnostics and tests by deterministic term/symbol/reference matching
   — no embeddings — so the model is never handed the whole repository.
7. **Never crash, never fabricate.** Every CIUE tool returns `(text, data)` like
   every other code tool, with structured refusals and a bounded compact payload.
   Initial indexing is asynchronous; a query refreshes stale data incrementally.

**Why.** LSP wrappers alone cannot answer "what depends on this file" or "what
tests cover this symbol", and they fail the moment a server is missing. An engine
that degrades to a real structural index, names its source, and reuses the existing
safety and tooling gives Eclipse repository-level software engineering without
duplicating infrastructure or pretending to a capability it does not have.

**Consequences.** New packages `python/harness/code/intel/` and
`intel_tools.py`; a new route group `routers/code_intel.py`; `policy.py` gains
`INTEL_WRITE_TOOLS`/`INTEL_READ_TOOLS`; both agent allowlists and `CHAT_CODE_TOOLS`
gain the tools (the pinned chat-set test is updated in place);
`ToolContext.code_intel_runtime`; `AgenticService` owns one `CodeIntelRuntime`
(started lazily, stopped with the runtime). No new third-party dependency is
required (Tree-sitter is optional; LSP is stdlib subprocess + JSON). Tests:
`test_intel{,_tools,_lsp,_api}.py` + fixtures + a fake language-server subprocess.
Architecture: `docs/harness/code-intelligence.md`.


## ADR-H129 — Code execution is an orchestrated lifecycle over the one sandbox, not a second terminal

**Status:** Accepted (2026-10-06)

**Context.** Eclipse could run individual allowlisted commands (`command_run`),
open persistent shells and manage background processes (the terminal subsystem),
and compute a derived metric in the analysis sandbox. It could NOT take a project
through the whole loop a coding agent needs: detect the language and runtime, build,
run, discover and run tests, normalize compiler/runtime/test failures into structured
diagnostics, and iteratively repair until verification evidence exists. Adding each
language ad hoc (or a second shell wrapper) would have duplicated infrastructure and
let the model silently widen its own permissions.

**Decision.**

1. **A dedicated layer, not a terminal wrapper.** `python/harness/execution/`
   owns the lifecycle. The terminal subsystem keeps interactive OS control; the
   execution layer owns language/runtime/entrypoint/sandbox/resource/evidence. They
   share the low-level process primitive and the terminal's process manager (for
   long-running services) but their responsibilities stay distinct.
2. **One execution primitive.** Every one-shot run goes through the existing
   `code/sandbox.py` (`RunSpec` → `RawResult`): argv arrays, no shell, scrubbed
   environment, bounded lifetime, hard output cap, whole-process-tree kill. There is
   no second spawn path. A runtime adapter stages an inline program outside the
   workspace and returns an argv — it never executes.
3. **The orchestrator owns the lifecycle; adapters own language behaviour.** The
   orchestrator resolves project → language → runtime → context → prepare → run/
   build/test → collect diagnostics/artifacts/metrics → cleanup → store. A
   `RuntimeRegistry` maps a language id to a `RuntimeAdapter`
   (`detect`/`resolve`/`prepare_run`/`build`/`test`/`discover_tests`). Python,
   JavaScript, TypeScript, SQL and Shell ship; Java/Go/Rust/C/C++/C#/PHP/Ruby are
   declared and report UNAVAILABLE honestly until an adapter is registered.
4. **A strict, validated state machine.** `ExecutionState` is one enum; every
   transition is checked and a terminal state has no outgoing edges. A `finally`
   path always lands the machine on a terminal state and always removes the staged
   working directory, whatever happened.
5. **The model can never widen its own permissions.** The `ExecutionPolicyEngine`
   narrows the request's network/filesystem policy to the autonomy profile's ceiling
   and refuses an explicit widening (`NETWORK_NOT_PERMITTED`); forbidden secret names
   (`.env`, cloud/SSH/GitHub tokens, API keys) are refused (`SECRET_FORBIDDEN`), never
   silently dropped. Risk bands are DATA (SAFE…CRITICAL); a HIGH+ band requires an
   approval. The existing `code/policy.allowed_tools` still removes the write/execute
   tools structurally at `plan_only`.
6. **Evidence, never inference.** The `ExecutionVerifier` runs a bounded
   build→test→fix→rebuild→retest loop (`max_iterations`, wall-clock budget). A
   "passed" outcome is only produced from an actual `COMPLETED` execution with a
   real test summary; a compiler error/security block is never "fixed" by editing
   code, and no success is ever claimed without evidence. An unparsed test summary
   reports `parsed: false`, not a pass.
7. **Distinguish infrastructure from user-code failure.** `ErrorClass`
   (`USER_CODE_ERROR` / `BUILD_ERROR` / `TEST_ERROR` / `RUNTIME_ERROR` /
   `INFRASTRUCTURE_ERROR` / `SECURITY_ERROR` / `TIMEOUT` / `CANCELLED`) so an agent can
   choose retry / fix / stop / ask. `RetryPolicy` is category-driven: a timeout may
   retry; a compiler error, permission failure or sandbox violation must not.

**Why.** A coding agent cannot be trusted to invent its own execution semantics.
Making the sandbox the single primitive, the policy engine the single authority, the
state machine the single lifecycle, and evidence the single basis for success gives a
production capability that is secure by construction and honest by default — and it
extends by registering an adapter, not by editing the orchestrator.

**Consequences.** New package `python/harness/execution/` and route group
`routers/execution.py` (`/execution/*`, operator-gated); `policy.WRITE_TOOLS` /
`READ_ONLY_TOOLS` gain the tool names; `ExecutionStore` owns the `Execution*` tables
on the ONE `agent-memory.db` connection (never `eclipse-memory.db`/`jdds.db`);
`AgenticService` owns one `ExecutionService` (built after the terminal manager,
stopped with the runtime); 21 tools register on the SAME registry. No new third-party
dependency (SQLite is stdlib; PostgreSQL requires an optional driver and refuses
otherwise). Retrieval tools are prefixed `execution_`/`service_` to preserve the
code-agent's finance-tool guard. Tests: `test_execution_{unit,runtime,security,e2e,
tools}.py`. Architecture: `docs/harness/execution-architecture.md`.

## ADR-H130 - Git is a layered engine with a closed operation table and a separate VCS provider layer, not CLI wrappers

**Status:** Accepted (2026-10-06)

**Context.** Eclipse could read a git checkout's status (a fixed, argument-free
read in `code/fs/git.py` and `code/workspace.py`) and could run a closed
`git_read` command class, but it could NOT drive a project through a full Git
workflow: create a branch, stage selectively, commit, merge, rebase, resolve
conflicts, stash, tag, worktree, push safely, or open a pull request. The
tempting shortcut — wrap `git status`/`commit`/`push` with a shell string and let
the model pass arguments — would put an unbounded, un-recoverable, un-auditable
capability in front of an autonomous agent, with no risk classification, no
recovery, no journal, and no separation between local version control and remote
hosting.

**Decision.**

1. **A layered subsystem, not a wrapper.** `python/harness/git/` composes
   discovery, ONE controlled executor, machine parsers, a state machine, a safety
   engine, a recovery manager, an operation journal and a lock behind a single
   `GitService` facade. Tools and routes are thin adapters over it.

2. **A CLOSED operation table.** `catalog.py` is the only place a git argv is
   defined; `operations.py` validates every value (no leading `-`, no pathspec
   magic, no NUL, bounded). The model never supplies an executable, a flag or a
   shell fragment. A subcommand absent from the table is unreachable.

3. **The sandbox discipline extends to git.** The executor runs one fixed argv
   with NO shell, a scrubbed environment, `GIT_TERMINAL_PROMPT=0` (fail, never
   hang on a credential) and `GIT_EDITOR=true`/`GIT_MERGE_AUTOEDIT=no` (never
   block on an editor), under the per-repository mutating lock, with a bounded
   timeout and output cap.

4. **Machine output only.** Status/diff/log/blame/worktree/… are parsed from
   fixed machine formats (`--porcelain=v2`, NUL-delimited `--format`), never
   human-readable output that can drift between git versions.

5. **Risk is machine-readable; authorization is layered.** Every op carries a
   SAFE…CRITICAL band. The autonomy profile is the grant
   (`code.policy.allowed_tools`: `plan_only` removes writes + remotes,
   `edit_verify` keeps local writes, `approve_external` keeps remotes); the Git
   effect authorizer then requires a SINGLE-USE operator approval for any
   dangerous/destructive op and for EVERY remote action. A force push is
   `critical` and never the default.

6. **Recoverable by construction.** Multi-step operations are detected from the
   repository's own sentinel files on every call, never a cached flag; a conflict
   is a structured failure plus a persisted active-operation record; the journal
   records every mutation (sanitized); nothing discards work automatically.

7. **Local Git and remote hosting are separate.** Git is the local VCS; GitHub/
   GitLab/Bitbucket are remote collaboration providers behind `VCSProvider` with
   a normalized PR=MR model. Tokens come from operator-declared env-var NAMES and
   are never exposed; a remote result is never faked.

**Why.** An autonomous agent must not be able to destroy history, overwrite
unpushed work, force-push, or silently bypass hooks — and it must be able to
recover when a merge or rebase stops half-done. A closed table + a single
executor + a risk/authorization engine + a recoverable state machine + a journal
gives a capability that is secure by construction, honest by default, and
testable in isolation.

**Consequences.** New package `python/harness/git/` (+ `git/vcs/`); route group
`routers/git.py` (`/git/*`, operator-gated); the effect-authorizer composition is
extracted to `code/authorizers.py` (so `graph.py` stays under its ratchet);
`code/policy.py` gains `GIT_READ_TOOLS`/`GIT_WRITE_TOOLS`/`GIT_EXTERNAL_TOOLS` and
narrows them in `allowed_tools`; the Git tools register on the SAME registry via
`service.py` (`register_git_subsystem`), like the terminal and execution
subsystems; the fs subsystem's older read `git_status` tool is removed in favour
of the one richer engine tool (the `FileSystemService.git_status` method and the
`file_metadata` git awareness are kept). No new third-party dependency (the VCS
HTTP client is stdlib `urllib`). Tests: `test_git_{engine,mutations,security,tools,
integration}.py` (isolated temp repositories). Architecture:
`docs/harness/git-version-control.md`.

## ADR-H131 — The Application Runtime is a provider-agnostic lifecycle over the one sandbox and the one terminal

**Status:** Accepted (2026-10-06)

**Context.** Eclipse could run one-off snippets, build a project and run its
tests, and it had a real terminal (persistent processes, ports, trees). It could
NOT understand an *application*: discover its framework and package manager,
install dependencies, start its services, check whether it is actually healthy,
diagnose why it isn't, recover it, or track it across an Eclipse restart. The
tempting shortcut — a bag of `docker`/`npm` shell wrappers the model strings
together — would couple the agent to Docker and npm, bypass the sandbox, expose
secrets, and conflate "a process exists" with "the app works".

**Decision.**

1. **One provider-agnostic registry.** `RuntimeRegistry` holds package managers,
   container runtimes, compose, and the (empty, extension-only) Kubernetes/
   Terraform/cloud seams. Adding Kubernetes or AWS later means registering an
   adapter, not rewriting the engine. Adapters declare a CLOSED capability set,
   so no caller asks an adapter for a meaningless operation.

2. **One lifecycle.** `ApplicationRuntimeManager` owns DISCOVER → VALIDATE →
   PREPARE → INSTALL → BUILD → START → HEALTH → RUNNING → OBSERVE → STOP →
   CLEANUP and delegates every concrete action (discovery, argv, containers,
   ports, health, persistence). It never implements a language or an engine.

3. **Reuse, never rebuild.** Local services start through the EXISTING
   `TerminalManager`; every argv runs through the ONE `code/sandbox.py`; the
   autonomy boundary is the EXISTING `code/policy.py`; runtime state lives on the
   ONE `agent-memory.db`; runtime errors reuse the execution layer's diagnostic
   parser for their code location.

4. **`RUNNING` is not `HEALTHY`.** State (`DISCOVERED…RUNNING/DEGRADED/STOPPED/
   FAILED`) is explicit and validated; health is a SEPARATE report produced only
   by a passing process/TCP/HTTP/container/database/custom check. A service that
   starts but never answers becomes `DEGRADED`.

5. **Honest failures.** A missing runtime/manager/engine is a structured refusal
   (`RUNTIME_MISSING`, `PACKAGE_MANAGER_UNAVAILABLE`, `ENGINE_UNAVAILABLE`), never
   a silent switch or a fake success. A declared/lockfile package manager is
   authoritative (no pnpm→npm fallback). Reconciliation after an Eclipse restart
   believes a persisted `RUNNING` only when the live terminal still knows the
   process.

6. **Security by construction.** Every argv is a validated list — no shell, no
   string concatenation; names/images/ports/volumes/env keys are validated.
   Secret values never reach the model, logs or events (only `[SECRET]` and
   existence). Destructive ops (`container.rm`, `volume rm`, `rmi`,
   `compose down/rm`, `.env` writes) are `external_action` tools removed at
   `plan_only` AND require explicit authorization.

7. **Bounded recovery.** A single bounded diagnose→strategy→act→verify loop
   (`HARNESS_APP_RECOVERY_MAX_ATTEMPTS`, default 3, hard cap 10) records every
   attempt and never acts on an irrecoverable diagnosis. No `while true`.

**Why.** An autonomous agent that runs applications must be secure by
construction, honest by default, provider-agnostic, and testable in isolation —
exactly like the terminal, execution, code-intelligence and Git subsystems before
it. A registry + one lifecycle + reused primitives delivers that; a bag of
wrappers cannot.

**Consequences.** New package `python/harness/execution/application/`; route group
`routers/application.py` (`/runtime/*`, operator-gated); `code/policy.py` gains
`APP_RUNTIME_WRITE_TOOLS`/`APP_RUNTIME_READ_TOOLS` and narrows them in
`allowed_tools`; the tools register on the SAME registry via `service.py`; the
front door adds `application-{client,browser}.ts`, `/api/runtime/**` and an
Applications tab in the terminal dock. No new third-party dependency (the
container/compose adapters use the existing sandbox). Tests:
`test_application_{unit,runtime,security,tools,api,e2e}.py`. Architecture:
`docs/harness/application-runtime.md`.



## ADR-H132 - Orchestration, infrastructure and cloud are declarative CLI adapters over one base, and deployment is a bounded lifecycle

**Status:** Accepted (2026-10-06)

**Context.** ADR-H131 shipped the local Application Runtime with empty
Kubernetes/Terraform/cloud seams. Filling them the tempting way — a per-provider
module each re-implementing sandbox discipline, argv building and JSON parsing —
would multiply the security surface with every provider and couple the engine to
each CLI.

**Decision.**

1. **One `CliAdapter` base.** `kubectl`/`helm`/`kustomize`, `terraform`, and
   `aws`/`az`/`gcloud`/`wrangler`/`vercel`/`railway`/`render` are each a
   declarative configuration: `kind`, `binary`, `capabilities`, and a CLOSED
   `operations` table of `CliOperation`s (an `argv` builder + a `validator`).
   Argument validation, JSON parsing, the sandbox call and the availability probe
   live ONCE in the base. A new provider is data, not a new engine.

2. **The sandbox discipline is inherited.** Every operation runs through
   `code/sandbox.py` with a scrubbed environment, a bounded timeout and output cap,
   and NO shell. A resource name/namespace/image/file/command containing a shell
   metacharacter is a structured `INVALID_ARG` refusal.

3. **Honest availability, honest capabilities.** A missing binary is
   `ENGINE_UNAVAILABLE`; an adapter declares a CLOSED capability set drawn from
   `ALL_CAPABILITIES`, so no caller asks for a meaningless operation. Credentials
   reach a cloud CLI only through its OWN ambient mechanism — this layer never
   passes or reads a secret, and it reports only whether a declared credential env
   NAME is set.

4. **Deployment is a bounded lifecycle, not a shell call.** `DeploymentEngine`
   runs validate → build → test → package → deploy → verify, delegating build/test
   to the SAME package managers the local runtime uses and deploy to a cloud
   adapter. A `production` deploy requires explicit authorization; a deployment is
   `deployed` only when the provider accepts it — never claimed live from a status
   call alone.

5. **Authorization is layered and structural.** The cluster/infra/cloud MUTATIONS
   are removed at `edit_verify` and `plan_only` (`code.policy.allowed_tools`); every
   one is an `external_action` and is additionally gated at call time
   (`terraform_apply`/`terraform_destroy`/`k8s_delete`/`helm_uninstall`/
   `deploy_delete`/a production `deploy_run`). Reads stay available at every profile.

6. **A real CLI, not a wrapper.** `harness/cli.py` builds the SAME process-wide
   manager the agent tools and the API use, so the CLI, the agent and the UI cannot
   disagree. It is structured (`--json`), it refuses a destructive command without
   `--authorized`, and it adds no execution logic.

**Why.** The provider-agnostic registry promised in ADR-H131 only pays off if the
providers themselves are uniform and secure by construction. One declarative base
+ a closed capability contract + a bounded deployment lifecycle makes Kubernetes,
Terraform and seven clouds additive and reviewable, without multiplying the attack
surface or coupling the engine to any CLI.

**Consequences.** New modules `cli_base.py`, `orchestrators.py`,
`infrastructure.py`, `cloud.py`, `deployment.py`, `cache.py`, `cli.py`,
`scripts/eclipse.js`; 29 new agent tools (`k8s_*`/`helm_*`/`kustomize_*`/
`terraform_*`/`cloud_*`/`deploy_*`) in `k8s_infra_tools.py`; `code/policy.py` gains
`APP_RUNTIME_K8S_WRITE_TOOLS` and narrows it at `edit_verify`/`plan_only`; route
group `routers/application.py` gains the orchestrator/terraform/deploy routes;
front door `application-{client,browser}.ts` + `/api/runtime/**` + the Applications
provider footer. No new third-party dependency. Tests:
`test_application_{orchestration,deploy}.py`. Architecture:
`docs/harness/application-runtime.md`.
## ADR-H133 - Provider readiness, managed long-running CLI ops, staged promotion and a cross-application graph complete the Application Runtime

**Status:** Accepted (2026-10-06)

**Context.** ADR-H132 shipped the orchestration/infra/cloud adapters and the
deployment lifecycle. Four real gaps remained: (1) a missing CLI or an
unauthenticated provider was honest only at CALL time, never at boot; (2) a
long-running CLI operation (`kubectl port-forward`, `logs -f`) had no home, so it
was refused as a one-shot op; (3) a deploy was one-shot, with no staging→production
promotion or rollback-on-failure; (4) the runtime understood ONE application, not
a workspace of several.

**Decision.**

1. **Readiness is a first-class, non-secret report.** `provisioning.py` answers
   "is this machine ready to run/deploy THIS project" from the registry's
   availability probes plus each provider's own ambient-credential status. It is
   on `/health`, `GET /runtime/providers` and `eclipse providers`. A credential is
   never read; only whether a declared env NAME is set. An unknown auth state is
   `null`, never a fabricated boolean.

2. **Long-running CLI ops are managed processes.** `managed_cli.py` builds the
   argv for `kubectl port-forward` / `kubectl logs -f` and starts it through the
   EXISTING terminal process manager — tree-killed, cancellable, streamed, visible
   in the Processes UI. It reuses the SAME closed-argv validation as `CliAdapter`,
   so there is no second argument surface. A one-shot adapter still refuses a
   blocking operation; the managed bridge is the right home for it.

3. **Promotion is a staged, health-gated pipeline.** `DeploymentEngine.promote()`
   deploys staging, requires authorization to cross to production, and ROLLS BACK
   on a production failure. A staging failure never touches production. Every stage
   is a real `deploy()`; nothing is claimed live without a passing check.

4. **A workspace is a graph, not a list.** `app_graph.py` builds a deterministic
   dependency graph over several applications (declared in `.black-eclipse/app.json`
   or a monorepo heuristic), with a stable topological `startupOrder` (dependencies
   first) and `stopOrder` (dependents first); a cycle breaks honestly. `workspace_ops`
   drives the existing `start`/`stop` in that order. No second lifecycle.

5. **Metrics accrete into a trend.** An `AppRuntimeMetric` sample is persisted on
   each `metrics()` read, bounded by a retention sweep, and summarised honestly
   (`rising`/`falling`/`flat`/`unknown` — never a false `flat` from too few samples).

6. **The compose engine is the authoritative graph fallback.** When the tolerant
   reader finds no services, `docker compose config` resolves anchors/merges/
   includes via the SAME `ComposeAdapter`; the engine's answer wins.

7. **The remaining work is opt-in and testable.** The live provider tests are
   gated behind `BLACK_ECLIPSE_PROVIDER_IT` (never in `npm test`), mirroring the Git
   provider suite. The deploy job templates ship disabled and stay subject to the
   same per-action authorization as a manual deploy.

**Why.** A production runtime must be observable before it runs (readiness), must
be able to hold a long-running connection it cannot express as a one-shot, must
never leave production half-shipped, and must understand the shape of the thing it
is running. Each of these closes a real operational gap without widening authority
or duplicating a primitive.

**Consequences.** New modules `provisioning.py`, `managed_cli.py`, `app_graph.py`,
`workspace_ops.py`, `observability.py`, `policy.py`; `manager.py` stays under its
size ceiling by delegating to `observability`/`workspace_ops`; 5 new tools
(`runtime_metrics_history`, `workspace_graph`/`_start`/`_stop`, `k8s_port_forward`,
`k8s_logs_follow`, `deploy_promote`) → 103 application-runtime tools; new routes
`/runtime/providers`, `/runtime/workspace/graph`, `/runtime/{id}/metrics/history`;
CLI `providers` and `workspace` groups; `/health.runtimeProviders`; two deploy job
templates; a Providers UI tab; `test_application_{provisioning,workspace}.py` +
`test_application_provider_live.py`. No new third-party dependency. Architecture:
`docs/harness/application-runtime.md`.

## ADR-H134 — The browser is a provider-agnostic runtime, not Playwright wrappers

**Decision.** The browser capability is a first-class harness subsystem
(`python/harness/browser/`) with a layered design: `browser_*` tools on the ONE
`ToolRegistry` → `BrowserManager` (pool/sessions) → `BrowserSession` (state +
operations) → a `BrowserProvider` interface → a concrete backend. Playwright is
one provider (`LocalChromiumProvider`), never the abstraction; a raw Playwright
object is never exposed to the model. Observation is accessibility-first:
`browser_snapshot` returns the accessibility tree with Eclipse's own stable refs
(`@e1`…), and large pages page to disk. Every important action is
`action → observe → verify`. Security is a single policy engine (permissions
ALLOW/DENY/ASK, domain policy, destructive-action elevation, an explicit
untrusted-page boundary), with an ASK routed through the EXISTING single-use
approval store. `browser_exec` is a sandboxed program AST (no `eval`/`exec`, no
host access). Optional cloud/alternate backends implement the same interface and
report honest availability — none is faked. `browser_request_human` handles
CAPTCHA/MFA; automation never bypasses it.

**Why.** A browser is one of the highest-authority capabilities an agent can hold
(untrusted input, credentials, external actions). Modelling it as Playwright
functions would leak a raw object to the model, scatter policy across handlers,
and couple the runtime to one backend. A layered provider runtime keeps the
reasoning, planning, sessions, policies, evidence and tracing in Eclipse; lets a
private/local target always run locally and a cloud provider be optional; and
makes the security boundary structural rather than prompt-based.

**Consequences.** New package `python/harness/browser/` (tools, tool_admin,
tool_support, manager, session, router, providers, observation, resolver,
verification, vision, execution, policy, vault, profiles, store, trace, config,
errors, authorizers, schemas, capabilities); a new router `routers/browser.py`;
boot wiring in `service.py`/`main.py` (`start_browser`/`start_browser_sweeper`/
`stop_browser`, `/health.browser`); `BROWSER_TOOLS` added to the finance agent,
code agent and chat code profile; `code/policy.py` (`BROWSER_EFFECTFUL_TOOLS`,
narrowed at `plan_only`) and `code/authorizers.py` (the browser admission layer);
a prompt guidance block; `playwright>=1.62,<1.63` in `requirements.txt` and a
doctor probe (never auto-downloads the browser); tests
`test_browser_{unit,integration}.py` + the local test app `browser_app.py`;
architecture `docs/harness/browser-runtime.md`. Chromium is a separate one-time
download; its absence is an honest `BROWSER_UNAVAILABLE`, never a fake browser.

### Phase B — limitations closed (same decision)

`browser_vision` gained a REAL interpretation layer (`vision_model.py`) that
reuses the harness model runtime instead of returning only a screenshot; it is
honest (`available:false`) with no multimodal model. `inspection.py` adds
`browser_find`/`browser_highlight` for non-interacting disambiguation. Large
console/network/error dumps are bounded and paged to `artifactsRoot`. `browserbase`
became a genuine cloud backend (REST session + CDP attach with a vault-resolved
credential). 83 `browser_*` tools.

### Phases C/D — evidence, skills, delegation and fusion (same decision)

`evidence.py` records every consulted `http(s)` page on the run's EXISTING
`source_sink` (`SourceCollector`), so browser-derived facts reach the answer's
Sources panel without a second provenance shape; the browser feeds the Evidence &
Research Engine rather than inventing one. A bundled inert `system.browser-research`
skill teaches the workflow (progressive disclosure). `session_of` prefers a session
owned by THIS run/agent (`BrowserManager.list_active`) so a delegated subagent never
drives the parent's browser — delegation isolation is structural. `browser_visual_locate`
(`vision.locate`) surfaces DOM+vision fusion with a confidence rationale and a trace
event. `waiting.py` extracted from `session.py` to hold the size ceiling. 84
`browser_*` tools.

## ADR-H135 — Research is evidence-driven: search results are pointers, the model is never the source of truth

**Decision.** Web research is a first-class harness subsystem
(`python/harness/research/web_*.py`) with one explicit invariant: **search results
are NOT evidence.** A search result is a pointer (title/URL/snippet); only a
fetched, normalized, provenance-tracked, timestamped artifact becomes `Evidence`.
The pipeline is `intent → mandate → plan → provider registry (ordered fallback) →
search → extract → browser escalation → normalize → entity resolution →
EvidenceStore → freshness/point-in-time → source ranking → conflict detection →
deterministic calculations → claim verification → citation generation →
validation → coverage → synthesis → immutable snapshot`. Every material claim is
traceable claim → evidence → source → location; a claim with no evidence is
`UNSUPPORTED`, never a fact.

**Why.** An agent that treats a model (or a search snippet) as a source of truth
will fabricate plausible financial numbers, silently average disagreeing sources,
and leak future information into historical analysis. Eclipse is built for
financial research where verifiability is the product, so the invariants must be
structural, not prompt-based: point-in-time research fails closed on an unknown
publication time; syndicated news copies are grouped into source families and
never counted as independent; a difference between sources is explained (period,
currency, basis, estimate/report, revision) or disclosed as an unresolved material
conflict; critical metrics are computed deterministically, never by the model.

**Consequences.** New package `python/harness/research/web_*.py` reusing — never
duplicating — the existing retrieval layer, the TS web transport via the
`DataBridge` (`web_search`/`web_fetch`), the Browser Automation Runtime (escalation
only), `research.budget`/`periods`/`calculations`, the SSRF/redirect guards, the
untrusted-content boundary, and the ONE `agent-memory.db` connection for its
`EvidenceStore`. 21 read-only tools on the ONE `ToolRegistry` (`web_search`,
`news_search`, `company_search`, `academic_search`, `image_search`,
`video_search`, `web_extract`, `page_extract`, `pdf_extract`,
`structured_extract`, `research_plan`, `research_query`, `source_rank`,
`source_compare`, `claim_verify`, `citation_extract`, `citation_validate`,
`research_status`, `research_cancel`, `research_continue`, `research_update`);
`WEB_RESEARCH_TOOLS` in `agents.py`; operator-gated router
`routers/research.py` (`/research/web/*`). Fetched content is wrapped through the
`UntrustedContentBoundary` and is never obeyed; injected instruction-like pages
are preserved as evidence but never laundered into a finding. Tests:
`test_web_research_{unit,integration,tools,api,hardcore}.py`. Architecture:
`docs/harness/web-research-engine.md`.

**Hardening (same decision).** A deep run must not be hard-killed by the harness's
generic tool ceiling: `ToolDefinition.long_running` lets a tool's own budget be
authoritative, `ToolRegistry.execute` publishes the effective timeout on
`ToolContext`, and the engine self-budgets below it to return a bounded partial.
Incremental `update_research` is non-destructive (append a snapshot, return a
delta) — prior evidence is never deleted. Raw evidence text is bounded in the
tool/API view while the store keeps it whole; the process-wide status/cancel maps
are bounded; events are namespaced `webresearch.*`. Regression tests:
`test_web_research_hardening.py`.

## ADR-H136 — Browser observability is a content-free aggregate and a browser-free replay, never a second store

**Context.** ADR-H134 made the browser a provider-agnostic runtime with a
per-task `BrowserTrace`. Traces persisted, but there was no aggregate view over
all activity and no way to inspect a failure without re-opening a browser; cost
and structured logs were absent. This is Phase 8 of the browser roadmap.

**Decision.** Observability is two read-only surfaces over the EXISTING trace
record — neither is a new evidence store:

1. **`telemetry.py` — a process-wide, content-free aggregate.** Counters with a
   fixed vocabulary (sessions, actions, failures, timeouts, crashes, navigations,
   downloads, uploads, vision, provider failures), per-action and per-provider
   latency kept as sum/count/max (never a per-call list), error `category`
   buckets, a bounded structured-log ring queryable by code/level/category/
   session, and a cost model. The cost model records REAL measurements (browser-
   seconds split by the provider's `remote` capability, vision tokens, screenshot
   count, artifact/download bytes) and produces a **money figure only when the
   operator configured a non-zero rate** — otherwise `ratesConfigured:false` and
   `estimatedMicros:null`. Nothing here stores page text, a URL query or a secret.
   The aggregate is `RLock`-guarded because a counter method appends a log line
   while holding the lock.
2. **`replay.py` — a browser-free inspection path.** `replay_trace` reconstructs
   a stored `BrowserTrace` into a bounded (≤500 steps) timeline and a
   `failureAnalysis` naming the first failing step's code/category/plain sentence.
   It never opens a browser and never re-executes; an unverified step is reported
   unverified, and a clean trace yields `failureAnalysis:null`.

Tools/routes: `browser_replay` (on the ONE `ToolRegistry`); `GET /browser/telemetry`,
`/browser/cost`, `/browser/logs`, `/browser/traces/{id}/replay`; a small
content-free summary in `/health.browser.telemetry`. Every tool call records one
action attempt at the SINGLE registration seam (`_telemetry_wrap`), so no handler
carries telemetry code.

**Why.** Replay and telemetry are what make the harder phases debuggable and
trustable in production. Building them as bounded aggregates and a pure read path
— rather than a second database or a live re-run — keeps memory (the top
constraint) bounded, keeps secrets out of observability, and honours the harness
rule that data is never fabricated: an unmeasured cost is reported as absent, not
guessed.

**Consequences.** New modules `browser/telemetry.py` and `browser/replay.py`;
cost/observability config (`HARNESS_BROWSER_COST_*`, `HARNESS_BROWSER_TELEMETRY_LOG_CAP`);
`browser_replay` tool; four operator routes; `/health` grows a telemetry summary;
tests `test_browser_observability.py` + `test_browser_observability_api.py`.
`main.py` does not grow (routes live in `routers/browser.py`).

## ADR-H137 — Frame targets, a resolver-owned coordinate fallback and a real device catalog (Phase H)

**Decision.** The hardening phase closes four failure-path gaps as first-class
runtime behaviour rather than test-only workarounds:

1. **Frame scoping is part of a Target.** A `Target` may carry `frame` (an iframe
   selector, nested with `>>`). The resolver's `_locator_for` resolves every
   strategy inside `page.frame_locator(...)` when the target names a frame, so
   cross-frame ACTION routing and frame-scoped snapshots
   (`SnapshotEngine.build(frame=...)`) work on cross-origin/nested frames. This is
   data on the existing Target, not a new code path.
2. **Coordinate fallback lives in the resolver/session, not the model.** A
   coordinate-only target clicks at the pixel; a locator that cannot click an
   occluded/stale element retries a pixel click and reports
   `strategy="coordinates"` with `reResolved=True`. A dead provider session
   surfaces a structured failure, never a hang.
3. **Device emulation uses a real catalog.** `devices.py` resolves a descriptor
   from whichever catalog the runtime exposes (the Playwright instance's
   `devices`, a module export, or the driver's `local_utils`) and reports the
   applied viewport/UA/locale/timezone; an unknown device is an honest error.
   `context_ops.py` (extracted from `session.py` to hold the size ceiling) applies
   viewport/device changes and records overrides (`viewport_override`, …) so an
   emulation is observable.
4. **The injection boundary is asserted.** Adversarial test pages prove page
   content never changes a session's policy, permission levels, or the tool
   registry — the hard guarantee is the `wrap_untrusted` boundary, and the test
   pins it.

**Why.** The acceptance suite covered the happy path; the remaining risk lived in
frames, interception, device/permissions, recovery and injection. Encoding the
missing behaviours in the runtime (frames, coordinate fallback, device catalog)
means they are structural and reusable, not test scaffolding; and documenting the
failure paths makes them navigable.

**Consequences.** `Target.frame`; `Resolver._scope` (nested `>>` chains);
`Snapshot.frame`; `SnapshotEngine.build(frame=)`; `browser_snapshot.frame`;
coordinate fallback in `BrowserSession.click`; new modules `browser/devices.py`
and `browser/context_ops.py`; `browser_set_*`/`emulate_device` record overrides;
the local test app gains nested/cross-origin frames and adversarial pages; tests
`test_browser_hardening.py` (real Chromium) + `test_browser_hardening_unit.py`
(offline). `session.py` net-shrinks (device ops extracted) to stay under the size
ceiling.

## ADR-H138 — The provider layer is finished honestly: extraction is not interaction, and a failing backend falls back

**Context.** ADR-H134 named the optional providers; several were honest stubs with
declared capabilities. Phase 9 completes the provider story: a new backend
(Camofox), a real Browser Use adapter, Firecrawl as a true extraction backend, and
health-aware routing.

**Decision.** Four commitments, each preserving the "never fake a provider" rule:

1. **Extraction is not interaction.** Firecrawl declares `interactive:false` and
   its `launch` REFUSES, so a browser *interaction* can never select it; it is
   wired into the research engine's extraction path only (`web_extract`
   `backend:"firecrawl"` → Firecrawl `/v1/scrape`, falling back to the SSRF
   bridge). `web_search`/interaction never touch it.
2. **Camofox is a launch provider, not CDP.** Camoufox is Firefox-based
   (Playwright `firefox`), so the provider resolves a binary (the `camoufox`
   package resolver or `HARNESS_CAMOFOX_ENDPOINT`) and launches through the local
   provider with `executable_path`; an endpoint attaches over CDP. Its declared
   `cdp:false` tells the truth about the protocol.
3. **Browser Use is a real adapter when installed.** The adapter starts Browser
   Use's browser and hands Eclipse a `ProviderSession` to drive; Eclipse retains
   reasoning/sessions/policy/observation/tracing. An incompatible build emits
   `BROWSER_PROVIDER_UNAVAILABLE` — honest, never fake.
4. **Routing is health- and cost-aware.** `ProviderHealth` demotes a provider
   after consecutive failures and re-promotes on success, recording the demotion
   in the decision; `prefer_low_cost` orders fitting candidates cheapest-first
   (a RELATIVE hint, never a money figure); an explicit request overrides
   demotion. The fallback rationale is in the trace.

**Why.** The master spec forbids faking a provider; the honest way to "finish"
the layer is to make each backend either genuinely run on this machine or report a
precise reason, and to make a failing backend fall through deterministically
instead of poisoning a task. Keeping extraction and interaction distinct prevents
Firecrawl (or any fetch backend) from ever being mistaken for an interactive
browser.

**Consequences.** `PROVIDER_CAPABILITIES["camofox"]`; `CamofoxProvider`,
`BrowserUseProvider` (real adapter), `FirecrawlProvider.extract`; `PROVIDER_COST`
+ `ProviderHealth` + demotion/cost in `router.decide`; `LaunchOptions.executable_path`;
config `HARNESS_CAMOFOX_*`, `HARNESS_FIRECRAWL_ENDPOINT`,
`HARNESS_BROWSER_PREFER_LOW_COST`, `HARNESS_BROWSER_ALLOW_PRIVATE_REMOTE`;
`web_extract.backend`; tests `test_browser_providers.py`.

## ADR-H139 — Progress is persisted, browser values become claims only through the engine, and the three surfaces share one routing policy

**Context.** Phase 10 completes the planner/workflow/cross-engine story. The
runtime already had evidence, skills, delegation isolation and visual fusion; what
remained was a visible progress surface, a second financial research workflow,
one documented hand-off rule across the three information surfaces, and a legal
path from a browser-read value to a verified claim.

**Decision.**

1. **Progress is a persisted task, not a stream of per-action events.** `browser/
   task.py` records a bounded checklist (`BrowserTask`) with per-step status,
   emitted as `browser.task.*` AND persisted to `agent-memory.db`. A user watching
   a long run sees “open SEC → search → find filing → download → extract”, and the
   progress survives the call that produced it (a per-action event is gone once
   streamed).
2. **A browser value is a candidate, verified only through the engine.** `browser/
   bridge.py` builds engine `Evidence` from a real `http(s)` URL + observed text
   (never fabricating provenance) and then runs the engine's OWN
   `web_verify.verify_claim`. There is no second verifier; a claim not grounded in
   the observed page text is refused. This is the one legal path (ADR-H135's rule,
   extended to the browser).
3. **One routing policy across three surfaces.** `research/coordination.py`
   documents and implements “search finds → browser reads behind a login →
   computer-use reads a desktop app”, deterministically, sharing ONE evidence
   store. A browser-read value is marked a candidate.
4. **A second bundled financial workflow.** `system.sec-filing-research` follows the
   `system.browser-research` pattern: progressive disclosure, `status: disabled`,
   referencing only real browser/web tools, and pointing a figure at
   `claim_verify` rather than asserting it.

**Why.** Progress and a single routing rule are what make the three surfaces
usable together instead of three overlapping tools; and the claim bridge is what
keeps the honesty invariant intact as the browser grows more capable — a browser
number can never bypass the engine's verification.

**Consequences.** New modules `browser/task.py` (persisted `BrowserTask` table) and
`browser/bridge.py`; `research/coordination.py`; the `browser_task` tool + `GET
/browser/tasks`; the bundled `system.sec-filing-research` skill; tests
`test_phase10_coordination.py`. No new evidence store — the browser still feeds the
engine's collector.

## ADR-H141 — The lifespan is its own module, the prompt ceiling narrows, and the three surfaces share one page (Phase S)

**Decision.** Stabilization is three process commitments, each made structural:

1. **Split, don't raise.** `main.py`'s FastAPI lifespan boot/shutdown wiring moved
   to `harness/boot.py`; `main.py` dropped from ~1018 to ~955 lines (under the
   1200-line hard ceiling) and was REMOVED from the size ratchet rather than having
   its number bumped. `main` re-exports `lifespan`, `identity_boundary`,
   `deployment_exposure` and `IDENTITY_BOUNDARY` so the public surface is unchanged.
2. **The prompt ceiling narrows.** The finance-agent prompt was trimmed of a
   redundant worked example and the ceiling LOWERED from 23300 to 23025 (its
   measured size) — the ratchet bites again instead of being widened once more.
   No honesty/authority rule was removed to hit the number.
3. **One page for the three surfaces.** `docs/harness/research-surfaces.md` is the
   single "which surface answers which question" page; `web-research-engine.md`,
   `browser-runtime.md` and `computer-use.md` all cross-link to it, and
   `NAVIGATION.md`'s trigger table names it.

**Why.** A ratchet that is only ever raised is not a ratchet, and god files
reappear when the answer to growth is always "split it later". `main.py` had grown
across three separate features; extracting the lifespan makes the route surface and
the boot sequence separate concerns. The three engines had drifted into
overlapping prose about who answers what; one shared page is the fix.

**Note on S.1 (concurrency).** Phase S also names a process hazard — multiple
writers committing into shared files, sweeping unrelated changes together. That is
a working-practice rule (serialize writers or use short-lived branches), not code;
it is recorded here and in the changelog rather than enforced by a hook.

**Consequences.** New module `harness/boot.py`; `main.py` shrinks and leaves the
ratchet; prompt ceiling 23300 → 23025; new doc `research-surfaces.md` cross-linked
from the three engine docs and `NAVIGATION.md`; tests
`test_phase_s_stabilization.py`.
## ADR-H140 — Computer Use is honest by construction: enforcement, native backends and challenge stops

**Context.** The Computer Use Engine shipped production-grade and Windows-only, but
a review found several claimed behaviours were not actually enforced or wired, and
the "unavailable by default" gaps (OCR, accessibility, vision, CAPTCHA handling)
were reported rather than closed. This ADR fixes the intent: every advertised limit
must be enforced, every backend must be real-or-honest, and a security challenge is
a human hand-off.

**Decision.**

1. **Advertised limits are enforced.** `max_actions` and `action_timeout_seconds`
   are no longer dead config: `ComputerCore.act` wraps every handler in
   `asyncio.wait_for` (timeout ⇒ `COMPUTER_TIMEOUT`, verdict `retry`) and a
   monotonic `session.actions_started` counter (over budget ⇒ `BudgetExceeded`,
   `COMPUTER_BUDGET_EXCEEDED`, verdict `abort`). A dry run still counts as an
   attempt, matching what `capabilities().limits` promises.
2. **Config fields have consumers.** `vision_model` overrides the resolved model
   id in `service._build_vision_router`; `ocr_enabled=false` disables OCR; the
   finance allowlists (`finance_allowed_apps/accounts/instruments`, with
   `HARNESS_COMPUTER_FINANCE_ALLOWED_*` env overrides) are wired into
   `build_firewall_from_config`. A cloud vision model is wired as the CLOUD backend,
   so a sensitive frame is refused rather than silently sent to it.
3. **Native backends are the default where the OS provides one.** `build_ocr_engine`
   `auto` prefers the OS-native OCR (`Windows.Media.Ocr` via the optional `winsdk`
   package, engine id `winocr`), then Tesseract. The `Pillow`, `uiautomation` and
   `winsdk` extras are declared in `requirements.txt` (Windows markers) and
   installed/repaired by `setup-python.js` / `doctor.js`. Every backend stays
   honest: absent ⇒ `available:false` with a reason.
4. **A security challenge is a human hand-off.** `security.detect_challenge` matches
   CAPTCHA/MFA/biometric markers; `ComputerSession.detect_challenge` scans the
   foreground window; the core refuses BEFORE delivering input (so nothing is
   clicked into the challenge) and returns `HumanInterventionRequired`
   (`COMPUTER_HUMAN_REQUIRED`, verdict `ask_user`). The new effectful
   `computer_request_human` tool lets the agent ask explicitly.
5. **Screen text is scanned, not only wrapped.** `security.scan_injection` (reusing
   the browser vocabulary) flags on-screen text posing as instructions; the
   UNTRUSTED wrapper gains a warning. The hard guarantee remains the wrapper + prompt.
6. **Background-first delivery is uniform.** Pointer move, scroll, drag and mouse
   down/up now honour `background` (posted WM_* messages in the target's own child
   hierarchy) as well as `foreground`, and foreground focus is restored after an
   escalation.
7. **Platform breadth is real-or-honest.** `drivers/linux.py` (ctypes X11/XTest)
   and `drivers/macos.py` (ctypes Core Graphics/AX) are real drivers with matching
   accessibility providers (`accessibility/linux.py` AT-SPI, `accessibility/macos.py`
   AX). Wayland-only Linux and any OS without a backend fall to a genuine
   `NullDriver`. macOS TCC permissions are probed, never fabricated.
8. **Sessions are serialized on the one physical desktop.** `broker.py` holds a
   machine-wide control lease for the duration of a single action, so concurrent
   sessions queue rather than interleave input; the per-session human takeover
   lease is unchanged.
9. **Isolation is a declared seam, not a claim.** `desktop.py` exposes a
   `DesktopProvider` (local today; Windows Sandbox / headless Xvfb declared), so
   `headless_desktop` stays False until a genuine provisioner exists.
10. **Adapter knowledge is honest about verification.** Adapters carry
    `verified`/`verified_note` (False = a knowledge record) and `looks_busy`/
    `looks_ready`; only the opt-in live rig marks one verified.

**Why.** "Ready on Windows" is only true if the limits are real, the common backends
exist without extra setup, and money/security still stop for a person. Honesty is
the invariant: an absent backend degrades to a reason, never a fake desktop.

**Consequences.** New `ocr/windows.py` (`WindowsOCREngine`); `errors.BudgetExceeded`;
`security.detect_challenge` / `scan_injection`; the `computer_request_human` tool
(and `EFFECTFUL_TOOLS`/`COMPUTER_EFFECTFUL_TOOLS`); driver background mouse paths;
`requirements.txt` extras + `setup-python.js`/`doctor.js` repairs. New
`drivers/linux.py`, `drivers/macos.py`, `accessibility/linux.py`,
`accessibility/macos.py`, `broker.py`, `desktop.py`; adapter verification status.
Tests: `test_computer_hardening.py`; the opt-in `test_computer_apps_live.py`.
VM/headless desktop provisioning remains the one open item.

## ADR-H142 — Isolated desktops are a provisioner seam: real Xvfb, declared Sandbox, honest fallback

**Context.** Computer Use ran every session against the operator's one physical
desktop, so `broker.py` could only *serialize* agents (preventing corruption, not
giving isolation). True multi-agent control needs a separate desktop per session,
and the earlier `DesktopProvider` seam was a capability descriptor with no
lifecycle.

**Decision.**

1. **A provisioner owns a session's desktop lifecycle.** `desktop.py` now defines
   `DesktopProvisioner.create/destroy` returning a `DesktopInstance` (its own
   driver, display, process). `ComputerManager` provisions per session: the local
   provisioner wraps the process driver; an isolated provisioner gives the session
   its own.
2. **Xvfb is real.** `X11HeadlessProvisioner` allocates a free display, spawns
   `Xvfb :N`, waits for the socket, and starts a `LinuxX11Driver` bound to that
   `DISPLAY`. The spawn/socket probes are injectable, so create→attach→teardown is
   fully tested without Xvfb installed; on a Linux host it runs for real.
3. **Windows Sandbox stays honestly unavailable.** `WindowsSandboxProvisioner`
   reports `available:false` because a host Win32 driver cannot attach to a
   sandbox session; it needs an owned RDP/VM display first.
4. **Isolation is opt-in and cannot break zero-config.** `isolation.mode`
   (`off|auto|on`, default `off`) picks the backend; absence of the backend falls
   back to the local desktop with a reason. `headless_desktop` is true only for a
   genuinely provisioned isolated desktop.
5. **Isolated sessions skip the machine broker.** A session with its own display
   neither waits on nor blocks the shared-desktop lease, so N agents run
   concurrently on N desktops; shared-desktop sessions still serialize.

**Why.** The one honest line is unchanged: isolation is real or it is not claimed.
The injectable lifecycle makes a platform-specific backend verifiable in CI, and
the opt-in default preserves `npm install && npm run dev`.

**Consequences.** `desktop.py` gains `DesktopProvisioner`/`DesktopInstance`/
`build_provisioner` and the Xvfb/Sandbox provisioners; `config.py` gains
`isolation*`; `manager.py` provisions/tears down per session and reports the
provisioner + broker in `capabilities()`; `session.py` marks `isolated`;
`LinuxX11Driver` takes an explicit `display`. Tests: `test_computer_hardening.py`.
Still open: Windows Sandbox attach and Wayland (portal) isolation.

## ADR-H143 — Remote/isolated desktops attach through a contained window; Wayland goes through grim/ydotool

**Context.** ADR-H142 built the provisioner lifecycle with a real Xvfb backend and
declared Windows Sandbox, RDP and Wayland unavailable. Those three share one
problem — the guest desktop is not addressable by the host's own SendInput/BitBlt —
and Wayland has no global input/capture API at all.

**Decision.**

1. **One attach mechanism: `WindowDriver`.** `drivers/window.py` wraps a base
   platform driver and scopes every operation to ONE contained desktop window
   (capture the window rectangle; translate window-local coordinates to absolute
   foreground events). It is the honest bridge for any desktop that renders inside
   a host window — Windows Sandbox, RDP, a VM console.
2. **The guest gets a real (OCR-derived) element tree.** The guest's native
   accessibility tree is not host-visible, so `WindowDriver.accessibility_tree`
   reads the contained window's pixels and turns OCR words into an `AXNode` tree
   (roles/text/absolute bounds), cached briefly. It is labelled `source=ocr` and
   returns None (accessibility False) when no OCR backend exists — never invented.
3. **Input is background-first, then foreground.** `WindowDriver` posts background
   input when the base driver supports it and escalates to foreground (verified by
   the core) otherwise, so a contained desktop gets the same safe delivery ladder.
4. **Windows Sandbox is real-or-honest.** `WindowsSandboxProvisioner` launches
   `WindowsSandbox.exe`, waits for the client window, and attaches a
   `WindowDriver`; absence (non-Pro/Enterprise, virtualization off) falls back to
   local with a reason. Launch/probe are injectable so the lifecycle is tested
   without the feature enabled.
5. **RDP is real-or-honest.** `RdpDesktopProvisioner` spawns `mstsc` against
   `rdp.host`/`rdp.file` and attaches to the session window. Eclipse never handles
   the credential — it relies on the operator's CMDKEY/`.rdp`.
6. **Wayland gets its own (headless) compositor + tools.** `WaylandDriver` captures
   via `grim` and inputs via `ydotool`, reporting each capability per-tool.
   `WaylandHeadlessProvisioner` spawns a **nested headless compositor**
   (`wlheadless-run` wrapping `sway`/`weston`, or their own `--headless` backend)
   on a private `XDG_RUNTIME_DIR` socket and attaches the driver — a genuinely
   isolated desktop, not just the shared session.
7. **Zero-config and isolation semantics are unchanged.** All backends are opt-in
   (`isolation.mode`), fall back to local with a reason, and an isolated session
   still skips the machine-wide broker.

**Why.** The blocker was never "no code" — it was "no addressable surface". A
contained-window driver turns an unattachable guest into a scoped, honest one, and
naming the limits (best-effort input, no guest AX) keeps the honesty invariant
intact.

**Consequences.** New `drivers/window.py`, `drivers/wayland.py`;
`WindowsSandboxProvisioner`/`RdpDesktopProvisioner`/`WaylandHeadlessProvisioner`
+ `_construct` in `desktop.py`; `config.py` `rdp_host`/`rdp_file`
(`HARNESS_COMPUTER_RDP_*`); driver factory `wayland`/`window`; opt-in live test
`test_computer_xvfb_live.py`. Still open: a *native* guest accessibility bridge
(the OCR tree is a real but weaker substitute), and full-unicode typing on
Wayland/X11.

## ADR-H144 — An "Always allow" permission is a separate, revocable standing grant, not a repeatable approval

**Context.** ADR-H92 made every effectful approval single-use and explicitly
deferred a standing grant. In practice a user running `python3`, `npm` or `git`
in a chosen folder is re-asked for every new command string, because the approval
is digest-bound to the exact command. The fatigue is real; the fix must not weaken
the single-use guarantee or let a misread toggle run something destructive.

**Decision.**

1. **A grant is a separate record, not a longer-lived approval.**
   `python/harness/grants.py` (`GrantStore`, table `StandingGrant` on the ONE
   `agent-memory.db`) stores `(kind, scope, pattern)` — one program/tool in one
   workspace. `McpApproval` is untouched: it stays single-use. A grant removes the
   *asking*; the store still authorizes nothing by itself.
2. **Grants are consulted BEFORE a request is created, never instead of the
   classification.** Each authorizer (shell, terminal, terminal subsystem, MCP,
   Git) checks `grants.matches(kind, scope, pattern)` first. A `deny`-classified
   command and an unknown MCP effect are refused before the check, so a grant can
   never make a destructive action run. A match emits `approval.granted` and the
   run proceeds — no card.
3. **Only an operator can mint a grant, and only from a real approval.**
   `ApprovalStore.remember_grant()` builds the grant from the pending row's OWN
   `grantPattern`/`grantKind`/`grantScope` columns (set by the authorizer), so a
   caller can never name an arbitrary pattern. The decide routes pass `remember`
   only on an approve. High-risk actions and dangerous/destructive/critical Git
   ops carry no pattern, so "Always allow" is never offered.
4. **Grants are listed and revoked by a dedicated surface.** `GET /grants` +
   `POST /grants/{id}/revoke` (operator-gated), fronted by
   `src/lib/harness/grants-client.ts` and the `StandingGrantsPanel` (Code ›
   Approvals). Revocation is immediate and idempotent.
5. **The request is never silent.** An `approval_request` plays the `notification`
   cue and raises the shared toast/OS notice, so a paused run is not missed.

**Why.** Single-use remains the authorization invariant; the grant is a narrow,
labeled, revocable convenience over the *prompt only*. Scoping to a program (not
the exact command) is what actually reduces fatigue, while keeping a denied or
destructive command impossible to remember.

**Consequences.** New `grants.py`, `routers/grants.py`; additive columns on
`McpApproval`; `ApprovalStore.grants`/`remember_grant`; every authorizer gains one
grant check and sets the `grant*` fields; `remember` on both decide routes; the
redesigned `ApprovalCard` (emerald, no yellow) with Allow once / Always allow /
Cancel; `ALERT_NOTIFY_EVENT` moves to `lib/alerts/browser-notifier.ts`. ADR-H92 is
unchanged for the store. Tests: `python/tests/test_standing_grants.py`.

## ADR-H145 — Authentication is opt-in and auto-engages off loopback; the front door is the boundary, not the runtime

**Context.** BlackEclipse shipped as a single-user local app with no
authentication and no tenancy isolation, and every layer said so honestly: the
Python `deps.py` hardcoded `authentication: False`, `api-guard.ts` warned on a
public bind, and `/health` reported the gap. That is correct for a local tool and
not enough for any deployment reachable by another machine, where "no
authentication" is a real hole rather than a design choice.

**Decision.** Authentication is OPT-IN and AUTO-ENGAGES at the moment the app
could be reached by another machine, and it is enforced at the FRONT DOOR (the
Next.js app an external caller actually hits), not deep in the Python runtime:

1. **One mode resolver** (`src/lib/auth/config.ts`). `HARNESS_AUTH=required|off`
   wins; unset resolves to *required* on a non-loopback bind or a production
   build, and *off* on a local dev bind. This preserves zero-config: `npm run dev`
   on localhost stays accountless, and a public bind stops being silently open.
2. **Fail closed, never silently.** When auth is required but
   `HARNESS_AUTH_SECRET` is missing, requests get `503 AUTH_MISCONFIGURED` with an
   instruction; the doctor reports the posture at boot.
3. **Two layers, because the Edge runtime cannot open SQLite.** `middleware.ts`
   (Edge) does the coarse gate — a validly signed session cookie for every page
   and `/api/**`, except `/login` and `/api/auth/**`. `requireApiAuth` /
   `getAuthContext` (Node) do the authoritative check against the session row.
4. **Tenancy is the session's.** When auth is on, `scope` comes from the session,
   never the request body — a signed-in user cannot widen their scope. When auth
   is off, `userId`/`scopeId` remain self-asserted filter labels, exactly as before.
5. **Honest everywhere.** `/health`'s `identity` reports the real mode
   (`authentication`, `frontDoorAuth.{required,source,secretConfigured,misconfigured}`)
   instead of a hardcoded "not implemented". The app is never presented as
   multi-user secure unless the front door actually requires a login.

Passwords are `scrypt`-hashed with a per-user salt (Node built-in `crypto`); no new
dependency. Sessions are opaque server-side ids in `.black-eclipse/auth.db`
(gitignored); the cookie is `HttpOnly`, `SameSite=Lax`, `Secure` off loopback, and
signed with `jose` (already a dependency).

**Why.** A local research tool should not force a login on a single user; a
hosted one must not be open. One resolver that flips on reachability — plus a hard
fail-closed when misconfigured — gives both without a config ceremony. Putting the
boundary at the front door is honest about where the trust line is: the Python
runtime is still reached only by the front door over loopback / the operator
token, and this protects the surface an external caller can actually reach.

**Consequences.** New `src/lib/auth/` (`config`, `store`, `session`, `token`,
`server`, `handlers`), `src/middleware.ts`, `src/app/login/page.tsx`, the four
`/api/auth/*` routes, a `better-sqlite3` ambient type, and a `doctor.js` auth line;
`deps.identity_boundary` and `IDENTITY_BOUNDARY` reworded to the opt-in truth;
`python/tests/test_identity_tenancy_boundary.py` updated and extended; docs
`docs/harness/authentication.md`. With `HARNESS_AUTH=off`, the old no-auth,
no-tenancy reality still holds and must stay on a trusted local machine.

## ADR-H146 � Vision is one orchestrator, native-first, with deterministic-first and an untrusted-input boundary

**Context.** Eclipse needed a production multimodal capability. The Computer Use
and Browser subsystems already had narrow, per-subsystem vision helpers
(`computer/vision/`, `browser/vision_model.py`) that re-used the model runtime,
and the model-capability registry already declared a `vision` capability. A new,
independent "vision stack" would have duplicated provider selection, OCR,
screenshots and the model construction path.

**Decision.**
1. **One orchestrator, one seam.** `vision/orchestrator.py` owns
   resolve?preprocess?store?route?capability?cache?dispatch?fallback?telemetry.
   Tools are thin adapters; no handler picks a provider or calls a model directly.
2. **Native-first.** If the run's own model accepts images, the image goes to it.
   The auxiliary vision model is a fallback, selected through the existing model
   registry with the runtime's same-provider/keyless-local rule. Routing is pure
   data and testable without a model.
3. **Deterministic-first.** OCR before a model; OCR-then-model grounding; PDF text
   layer before the model; a pixel diff before a model describes it; chart numbers
   are verified against deterministic market data through the existing bridge, and
   a visual/numeric disagreement is reported with market data authoritative.
4. **Untrusted input.** URL fetching re-uses `mcp.ssrf` on every hop; byte/pixel
   ceilings plus Pillow's bomb guard; recognized in-image text is scanned and
   DELIMITED as untrusted data (re-using `research.web_security`), so text inside
   an image is data, never an instruction.
5. **Binary outside relational data.** Images are content-addressed on the
   gitignored filesystem tier; only metadata is a `VisionAsset` row on the ONE
   `agent-memory.db` connection.
6. **No Redis.** The cache is a bounded in-process TTL store keyed over image
   hash + model + provider + prompt + mode + preprocessing + schema version,
   consistent with the existing retrieval/investor-eye caches.
7. **Evidence without a new contract.** Observations become the existing
   `research.web_contracts.Evidence` and persist through `EvidenceStore`, with
   `contentTrust=UNTRUSTED`.

**Consequences.** New `python/harness/vision/` (contracts, config, errors, image,
fetch, load, storage, cache, capabilities, providers, routing, analyze, ocr,
grounding, documents, charts, compare, security, telemetry, tiling, evidence,
collector, orchestrator, tools); the `VISION_TOOLS` constant in `agents.py` on the
finance and code agents (all read-only); boot wiring in `service.py`
(`AgenticService.vision_assets`); the `vision` run-blob column on `HarnessRun`;
`vision` on `RunResult`/`client.final`; TS `vision-view.ts` +
`src/components/chat/vision-panel.tsx`; tool labels in `response-model.ts`;
activity detail/summary for vision tools in `code/activity.py`; `pypdfium2` added
to `requirements.txt`. The Computer Use and Browser vision helpers are unchanged
(the orchestrator complements, not replaces, their narrow per-subsystem needs).
Tests `python/tests/test_vision_{unit,orchestrator,tools,graph}.py` and
`src/lib/harness/vision-view.test.ts`. Docs `docs/harness/vision.md`.


### ADR-H146 (addendum) - capability closers: stdlib PDF, persistent visual memory, image generation

Three areas that were initially only "honest limitations" were implemented:

1. **PDF without pypdfium2.** `vision/documents.py` adds a dependency-free
   `_StdlibPdf` backend (text from content streams always; Pillow rasterization for
   standard-font pages). Each `DocumentPage` records `textMethod`/`rasterMethod`, so
   the method is never hidden; `pypdfium2` remains preferred. `pdf_capabilities()`
   reports availability. No page is ever faked.
2. **Persistent visual memory.** `vision/memory.py` (`vision_remember` tool) persists
   a vision result through the SAME memory decision gate (`authorize_proposal` +
   `commit_decision`) - never bypassing it. Only a text summary is stored (never the
   bytes); the content-addressed `assetId` and regions/model/provider/confidence ride
   in `structuredData`; a sensitive/ephemeral result is low-importance with a 1-day TTL.
3. **Image generation.** `vision/generate.py` (`image_generate` tool) speaks the
   OpenAI-compatible `/images/generations` protocol, gated by the model's declared
   `image_generation` capability. It is registered `external_action` (effect
   `external_action`), approval-gated by the run's effect authorizer, and removed at
   `plan_only` via `code/policy.py` `VISION_EXTERNAL_TOOLS` - the same boundary every
   other external/paid tool uses. Failures are classified (`NO_VISION_MODEL`,
   `AUTH_ERROR`, `RATE_LIMIT`, `MALFORMED_RESPONSE`), never a placeholder image.

`VISION_TOOLS` gains `vision_remember` and `image_generate`; the `image_generation`
task profile (already present) routes generation; image-generation model families
(dall-e/gpt-image/imagen/stable-diffusion/sdxl/flux) are declared in
`model_runtime/catalog.py`. Tests `python/tests/test_vision_capabilities.py`.


## ADR-H147 - Document Intelligence is one adapter/orchestrator pipeline over the shared DocumentIR, reusing vision, the model runtime, the evidence store and the query engine

**Context.** Eclipse could see an image and read a PDF page, but had no
first-class document-understanding capability: no format adapters, no unified
intermediate representation, no OCR routing, no structured table/spreadsheet
extraction, no hybrid document retrieval, no document comparison, and no
document-aware provenance for the Evidence & Research Engine. The Vision
subsystem (ADR-H146) already owned OCR engines, PDF rendering, the model-call
path and the untrusted-input boundary; the Evidence Engine already owned the
`Evidence` contract and `EvidenceStore`; DuckDB and pandas were already present
for the SQL runtime; `agent-memory.db` was already the ONE runtime database. A
parallel "documents" stack would have duplicated all of them.

**Decision.**
1. **One subsystem, one pipeline.** A new `python/harness/document_intelligence/`
   package owns `validate → cache → detect → parse → OCR/vision → structure →
   entities → chunk → index → evidence → assess`. Tools are thin adapters; no
   handler decodes a file, picks a parser or calls a model directly.
2. **A unified DocumentIR.** `ir.py` defines the vocabulary every adapter emits
   (`DocumentIR`/`Page`/`Sheet`/`Block`/`Table`/`TableCell`/`DocumentImage`/`Section`
   /`BBox`/`Provenance`/`DateFacts`). Coordinates are never lost, each block
   carries its extraction method + confidence, and observed/extracted/inferred is
   explicit. Downstream stages read the IR, never raw bytes.
3. **Adapter per format, honest capabilities.** `adapters/` has one adapter per
   kind (PDF, DOCX, PPTX, XLSX, ODS/ODT/ODP, CSV/TSV, JSON/JSONL/XML/YAML/TOML,
   HTML, Markdown/TXT, image, EPUB, RTF, archive, legacy OLE). Each declares a
   `Capabilities` map, so a CSV is not asked to render a page and a PPTX is not
   asked for worksheets. OOXML is parsed with stdlib `zipfile`+`ElementTree`
   (lxml recovery when available), so no `openpyxl`/`python-docx`/`python-pptx`
   dependency is added.
4. **Deterministic OCR routing.** `ocr.py` runs the existing OS OCR engine first
   and only escalates to a vision-model transcription when there is no usable
   text or confidence is below `OCR_CONFIDENCE_THRESHOLD`. Method + confidence are
   recorded per page; a page with no text and no engine is reported, never faked.
5. **Reuse, never fork.** OCR engines, PDF rendering and every model call come
   from `harness.vision`; the model runtime is the only provider path; extraction
   results become the SAME `research.web_contracts.Evidence` through
   `EvidenceStore` with `contentTrust=UNTRUSTED`; tabular questions are computed
   with read-only SQL over DuckDB/pandas (`query.py`), never model arithmetic;
   tables live on the ONE `agent-memory.db` connection (`store.py`), binaries in
   the vision asset store, and the IR blob is metadata-only on the gitignored
   filesystem tier.
6. **Untrusted input.** `security.py` validates extension/MIME/magic and byte
   ceilings before any parser runs, refuses macro-enabled Office documents,
   detects archive/compression bombs (declared size, ratio, entry count, nesting)
   BEFORE extraction, SSRF-guards document URLs through `mcp.ssrf`, sanitizes HTML
   of active content, and re-uses the shared injection boundary so document text
   is DATA, never an instruction.
7. **Truthful states.** `processing.py` models
   `DISCOVERED→…→READY|PARTIALLY_READY|FAILED|CANCELLED`; a stage that cannot run
   is `UNAVAILABLE`/`SKIPPED` and the document is `PARTIALLY_READY`, never `READY`.
   Bounded retry (transient only) and a per-document timeout guard parsing.
8. **Hybrid retrieval, point-in-time, provenance.** `retrieval.py` fuses lexical
   scoring (deterministic, no embeddings — consistent with the harness's
   documented lexical stance) with structured filters over document/version/page/
   sheet/table/cell and the entity table. `compare.py` diffs two DocumentIRs
   structurally before any model prose. `DateFacts` preserves publication/filing/
   effective/period/retrieval dates.

**Consequences.** New `python/harness/document_intelligence/` (config, errors, ir,
contracts, security, base, adapters/*, ocr, render, entities, chunking, store,
retrieval, query, compare, evidence, processing, telemetry, collector,
orchestrator, tools); `DOCUMENT_TOOLS` in `agents.py` on the finance and code
agents (all read-only); boot wiring in `service.py`
(`AgenticService.document_store`); the `documents` run-blob column on `HarnessRun`;
`documents` on `RunResult`/`client.final`; TS `document-view.ts` +
`src/components/chat/document-panel.tsx`; tool labels in `response-model.ts`.
Tests `python/tests/test_document_intelligence_{unit,tools,security,graph}.py` +
fixture builder `document_intelligence_helpers.py` and
`src/lib/harness/document-view.test.ts`. Docs `docs/harness/document-intelligence.md`.
No new third-party dependency is added.


## ADR-H148 - Vision capability is detected per MODEL FAMILY, not per SDK kind; a text-only run model falls back to any available vision model

**Context.** The Vision subsystem reported "needs a vision-capable model
configured" even when the operator had vision-capable models. Two defects caused
it. (1) The `openai` capability-kind default declared `vision: SUPPORTED` for
EVERY model of that kind — but the `openai` SDK kind is shared by OpenAI, Ollama,
LM Studio, DeepSeek, xAI, Groq, Together and any OpenAI-compatible endpoint, most
of which serve text-only models. So a run model that could not see images was
nonetheless routed as native and received the image (a failed round-trip), while
genuine VLMs whose names were not catalogued stayed unrecognized. (2)
`plan_route`'s registry search called `findByCapability(VISION_SUPPORT)` with a
bare STRING, so the runtime iterated it character-by-character and matched no
model; and cross-provider fallback was refused even when a credential existed.

**Decision.**
1. **Per-family vision priors.** The `openai` kind default no longer claims
   vision. `MODEL_CAPABILITY_OVERRIDES` now declares the vision-capable families
   (gpt-4o/4.1/4-turbo/4-vision/4.5/5, o1/o3/o4, the whole Claude and Gemini
   families, grok-2-vision/grok-vision/grok-4, and open-weight VLMs: llava,
   qwen2-vl/qwen2.5-vl/qwen3-vl, minicpm-v, moondream, pixtral, llama-3.2-vision,
   llama-4, internvl, phi-3-vision/phi-4-multimodal, granite-vision, deepseek-vl,
   gemma-3, and a `vision`-in-name catch-all) AND the text-only families
   (gpt-3.5/gpt-4, o1-mini, deepseek-chat/reasoner, llama-3.x, qwen2.5/qwen3 text,
   mixtral, mistral, codestral, groq hosts, grok-2/3, …). Longest-substring
   matching keeps a specific entry ahead of a generic one.
2. **Native-first asks about the RUN'S OWN model.** `plan_route` reads the run
   model's capabilities DIRECTLY (`capabilities_for_model`), never a routed
   substitute, so a routed VLM's capability is never attributed to a text-only run
   model.
3. **The registry search is fixed** (pass a list, not a string) and runtime
   discovery is the default, so declared/discovered VLMs are always considered.
4. **Credentialed cross-provider fallback.** A different provider is usable as the
   auxiliary vision model when it is keyless-local OR its declared env credential
   is present (`models.provider_has_credentials`); a remote provider the process
   holds no key for is still never selected (ADR-H146 §31/§45). The local VLM
   family is also added to the Ollama/LM Studio/OpenRouter declaration lists.
5. **Document Intelligence routes through the vision orchestrator**, so an
   embedded-image analysis on a text-only run model gets a real vision model too.

**Consequences.** `model_runtime/catalog.py` (per-family vision priors),
`harness/models.py` (`provider_has_credentials` + local VLM declarations),
`vision/capabilities.py` (`capabilities_for_model`), `vision/routing.py`
(direct run-model caps, default runtime, list `findByCapability`,
credentialed cross-provider fallback), `document_intelligence/orchestrator.py` +
`ocr.py` (route image analysis/OCR-fallback through the vision orchestrator).
Tests `python/tests/test_model_vision_capability.py` (recognition matrix +
routing); the local-only vision test now asserts the invariant "never cloud"
rather than "no candidate". No new dependency.


## ADR-H149 - Market data is one gateway over declarative providers; the adapters stay on the TS bridge

**Status:** Accepted (2026-10-07). The Market Data Layer is the one market-data
surface for agents: fourteen capability tools (get_quote … stream_market_data)
call a single MarketDataGateway, which resolves the instrument, selects a
provider via a declarative ProviderRouter, fetches through the ONE read-only TS
bridge capability (market_data), normalizes to a canonical record, runs the
mandatory data-quality engine, and preserves provenance into the Evidence &
Research Engine. Agents never name a provider.

**Context.** The retrieval layer (
etrieval/) is provider-agnostic but shallow —
it serves quote/statements/news/profile, not order books, trades, funding, open
interest, options, FX or bonds. The market-data engine (scraper chain, yfinance
bridge, Yahoo chart, crypto connector, SEC, economics) already lives in Next.js,
which also owns the ONE secret store (provider-keys.ts) and the ONE hardened
outbound layer (connectors/security.ts#safeGet). Rebuilding an HTTP client or a
second secret store in Python would duplicate both.

**Decision.** Keep the *adapters* in TypeScript (one file per provider under
src/lib/harness/market/providers/) and keep *routing, normalization, quality,
caching, provenance, storage and streaming* in Python (python/harness/market/).
The Python runtime calls providers only through a single bridge capability,
market_data; it holds no provider key. Instrument identity is the bridge's
instrument master (the same one the retrieval layer uses), cached briefly and
never invented when the bridge is silent.

**Consequences.** ONE transport, ONE secret store, ONE instrument master; the
adapter registry is additive (a new provider is one TS file + one Python
descriptor row). Order books/streaming are real (Binance public REST/WebSocket),
not pollers. Known gaps are returned honestly (UNSUPPORTED_CAPABILITY for an
equity order book) rather than faked. websockets/httpx are pinned; when
websockets is absent, streaming reports STREAM_DISCONNECTED and REST is
unaffected. Tests: python/tests/test_market_{unit,gateway,streaming}.py +
src/lib/harness/market/bridge.test.ts. Docs docs/harness/market-data.md.

## ADR-H150 - The Quant Engine is a deterministic Python engine; strategies are data, and backtest simulation is separate from real-holdings accounting

**Context.** The harness needed real backtesting/research. The risk was the LLM
being asked to compute P&L/Sharpe/drawdown, or a demo engine returning
hardcoded metrics.

**Decision.** All trading math lives in `python/harness/quant/`, a modular
event-driven engine (`strategy`/`rules`/`indicators`/`data`/`orders`/
`execution`/`sizing`/`risk`/`portfolio`/`metrics`/`engine`/`store`). A strategy
is a structured, serializable **specification** (universe, timeframes,
indicators, a rules DSL, risk, sizing, execution), not arbitrary code — so it is
versionable, validatable and safely deterministic. The LLM only authors/edits
specs and calls tools. Market data is read through the ONE Market Data Gateway
(the engine never calls a provider). Point-in-time correctness is enforced by a
documented bar-processing order: a `data_available_at` per bar, causal
indicators (NaN warm-up), next-bar fills, and higher-timeframe alignment that
only exposes a higher bar once it has closed. Heavy result series are gzipped
artifacts under `.black-eclipse/quant/`; metadata is on the ONE `agent-memory.db`
connection. Capabilities are reported as available/partial/unsupported. The
research engines — optimization (grid/random/evolutionary/Bayesian), walk-forward
(strict no-test-leakage), Monte-Carlo, and sensitivity/robustness — are
implemented, tested, exposed as tools and routes, and advertised `available`;
only options (Phase 7) and futures remain unsupported/partial and are NOT
registered as tools. Portfolio backtests build one execution simulator + risk
engine per strategy binding (per-strategy costs/limits); `historical` spread uses
a per-bar spread column when present, else warns.

**Consequences.** One deterministic source of truth for trading calculations;
reproducible experiments (seed + engine version + dataset + assumptions);
honest capability reporting. The backtest simulation portfolio
(`quant/portfolio.py`, float, long/short, bar-loop) is deliberately separate
from the Portfolio Accounting Engine (`harness/portfolio/`, Decimal, tax lots),
which refuses shorts and is oriented to real holdings; for long-only runs the
two MUST agree on realized P&L, which a test asserts. Reusing the accounting core
for simulated transactions is deferred and would be an extension of the core,
not a fork. Tests: python/tests/test_quant_*.py (57) +
src/lib/backtest/backtest-client.test.ts. Docs docs/quant-engine.md.

## ADR-H151 - Unified search is a provider-agnostic retrieval layer over a dedicated SQLite vector + FTS index (not pgvector)

**Context.** Eclipse needed first-class semantic/vector search across documents,
research evidence, agent memory, experiences and skills, with hybrid retrieval,
reranking, provenance and citations. The reference design assumed PostgreSQL +
pgvector. This repository is deliberately **SQLite-first and zero-config**
(`npm install && npm run dev` must never require manual setup) and already had a
deterministic lexical retrieval layer (`retrieval/`) and dedicated SQLite index
stores (`code/intel/persistence/index.py`).

**Decision.** Introduce `python/harness/search/` as the ONE retrieval layer and
store its index in a **dedicated SQLite file** (`.black-eclipse/search/search.db`,
`ECLIPSE_SEARCH_DB_PATH`), mirroring the code-index precedent rather than adding
a second database engine. Introducing PostgreSQL/pgvector would break the
zero-config promise, which is a concrete architectural reason to deviate from the
reference plan (spec §6 permits this). The embedding-provider abstraction,
vector-space/version registry, hybrid retrieval, reranking, provenance and
citations are storage-agnostic, so the store can be swapped for pgvector later
without touching callers. Keyword search uses SQLite **FTS5 BM25** (no
Elasticsearch); vectors are served by a real **sqlite-vec `vec0` ANN index** per
vector space when the extension is present (the KNN is restricted to the
caller's authorization buckets before scoring, so no unauthorized vector is ever
a candidate), and fall back to brute-force cosine when it is absent. Metadata
filters are indexed (`SearchDocumentMeta` + a distinct `documentType` column) and
compiled into the candidate SQL, and indexing is incremental by content hash. One
`SearchService` is constructed at boot (`search/bootstrap.py`) and reused by the
agent tools and the operator HTTP surface; per-run searches re-resolve the
embedding provider from the run's `ModelSettings`. Semantic search **degrades
honestly to keyword/FTS** when no embedding provider is configured — it never
fabricates a vector, and a fake provider is never registered. Authorization is a
SQL predicate compiled from the run's scope (workspace/owner/public), so results
are never scanned-then-filtered. Zero-config still works: with no provider the
layer is keyword-only.

**Consequences.** Real semantic + hybrid + keyword search with batching, caching,
retry/backoff, reranking, temporal/entity/metadata filters, dedup, parent/neighbor
context, an EvidenceStore bridge and an evaluation harness (Recall@K/Precision@K/
MRR/NDCG). The ANN ceiling and pgvector migration are explicit, documented
limitations, not silent gaps. Tests: python/tests/test_search_*.py. Docs
docs/harness/search-retrieval.md. Front door: `src/lib/harness/search-{client,types}.ts`,
`src/app/api/harness/search/[[...path]]/route.ts`, and the mounted Search
Intelligence tab.

## ADR-H152 - Automation is a first-class domain object; one scheduler decides WHEN, the runtime decides WHAT

**Decision.** The earlier `harness.jobs` scheduler (ADR-H108) is upgraded into the
Native Automation Engine (`python/harness/automation/`). An automation is a durable
domain object with a trigger (cron / interval / one-time / event / condition /
manual), an optional gate condition, an action, and execution / retry / concurrency
/ resource / permission / delivery policy — not a cron string. Two state machines
are kept strictly separate: the automation's LIFECYCLE (`draft/validating/active/
paused/disabled/archived`) and an EXECUTION's state (`triggered/queued/running/
waiting/retrying/completed/failed/cancelled/timed_out/blocked/skipped`); an invalid
transition is rejected with a code. Conditions are a small, safe expression language
evaluated THREE-VALUED (a missing operand is `UNAVAILABLE`, never silently false)
with persisted edge state, so `BTC.price < 90000` fires on FALSE→TRUE only and is
restart-safe. The engine is the ONE scheduler: due lookup is an indexed
`nextRunAt` query, event routing is an indexed `AutomationEventSubscription` join
(never a full scan), event delivery is deduplicated durably, work is protected by a
lease-based lock (expiry reclaims a crashed worker's execution), retries use
backoff + jitter and NEVER retry a non-retryable error class, and concurrency is
bounded by policy. Actions dispatch through the EXISTING runtime — `service.run` /
`run_skill` / `run_workflow`, the Task System (`service.tasks`) and the
Orchestration layer — so there is no second agent loop, tool registry or adapter.

**Why.** Automation had a scheduler but not a domain: it could not express a
condition, an event, a retry policy, a concurrency policy or a resource limit, and
its timezone field was stored but ignored. The risk of adding those as a SECOND
system was real — two schedulers, two ledgers, two execution paths. This ADR makes
the opposite choice: one definition model, one durable ledger, one scheduler, and
the legacy `/jobs` API becomes a thin ADAPTER (`automation/legacy.py`,
`routers/jobs.py`) over the same service, so existing clients and their tests keep
working while the implementation underneath is single.

**Consequences.** `Automation*` tables live on the ONE `agent-memory.db`;
`migrate_legacy_jobs()` imports existing `HarnessJob` rows and their run history
preserving ids and never deleting data. Every automation stores only a credential
REFERENCE (never a value) and validation refuses embedded secret-like keys; the
effective permission policy is deny-wins and approval is a single-use, digest-bound
`ApprovalStore` claim. Execution snapshots capture the effective configuration
(trigger/condition/action/policies) but NEVER credentials, so "why did it behave
this way" is answerable. Known honest limitations: token/cost limits are detected
at run end (providers bill per call, so they cannot be prevented mid-run); the
runtime is single-process (the lease makes that explicit and crash-safe rather than
promising multi-process throughput). Tests: `python/tests/test_automation_*.py`.
Docs: `docs/harness/automation-engine.md`. Front door:
`src/lib/harness/automation-{client,browser}.ts`, `src/app/api/automations/**`.


## ADR-H153 - One Event System: a canonical envelope + registry over a durable, indexed event store, bridged to the existing run bus

**Decision.** Eclipse gains a first-class Event System (`python/harness/event_system/`)
that owns the ONE canonical event model. An `EclipseEvent` carries a globally
unique id, a UTC timestamp, `type` + `version`, source, actor, correlation /
causation / trace ids, session / task / workflow / agent associations, priority,
a validated payload and metadata. A centralized `EventRegistry` declares each
event type (or namespace) with its schema, producer, allowed consumers,
permission, priority, retention, retry policy and sensitivity; names are never
scattered as magic strings. Events are persisted to an indexed `HarnessEventLog`
on the ONE `agent-memory.db` (plus `HarnessEventConsumer` for consumer-level
idempotency, `HarnessEventDeadLetter` for the DLQ, and
`HarnessEventSubscription` for declared subscriptions). The `EventBus` provides
`publish` / `publishMany` / `subscribe` / `unsubscribe` / `once` / `request`,
composable middleware (validation → authorization → redaction → enrichment →
persistence → routing → delivery → metrics), per-consumer async workers with
bounded queues (backpressure), exponential-backoff retry with jitter (never
retrying a non-retryable error class), idempotent consumers, a real dead-letter
queue, tracing and graceful shutdown.

**Why.** The runtime already emitted events in several places — the per-run SSE
`EventBus`/`RunEmitter`, orchestration and task event vocabularies, and the
Automation Engine's event routing — but there was no single durable event model:
no canonical envelope, no centralized naming/validation, no store queryable by
correlation / causation / task / workflow / agent, no consumer idempotency, no
DLQ, no replay and no console. The risk of the obvious fix was a SECOND bus and
divergent vocabularies. This ADR takes the opposite choice: the existing run bus
stays the low-latency live transport, and the new `EventBus` **bridges** to it —
ingesting every legacy event (reusing its id so dedup holds) and echoing new
typed events back — so there is one transport abstraction and one model. The
task publisher (`tasks/bootstrap.py`) now emits canonical names
(`task.created`, not `task.task_created`, and `workflow.created` for plans), and
the scheduler emits `schedule.triggered`, so a timed fire is an observable event
rather than a coupled Scheduler→Agent jump.

**Consequences.** Correlation and causation propagate automatically through
`contextvars` — a follow-up event created inside a handler inherits them without
the developer threading ids through every call. Sensitive events require an
operator actor and declared permissions are checked with the ONE permission
authority (`skills.permissions`); payloads are redacted (by key and by value
pattern) as a publish middleware so a secret can never reach the store. Replay
is explicit and three-mode (`observe` / `simulation` / `full`); `full` requires
operator authorization and destructive/financial types require confirmation, and
a replayed event is a NEW event (new id, `metadata.originalId`) so idempotency
keys on it and the replay fires. Built-in consumers are deliberately conservative
to avoid loops and storms: a memory-candidate extractor emits bounded
`memory.candidate.created` events (the Event Store is never agent memory), a
self-improvement trigger requests an `evaluation.started` at most twice per
correlation and never past depth 6, and a market sampler coalesces
`market.price.updated` into `market.snapshot.updated` so a price tick can never
cause one LLM call. Event→action rules reuse the Automation Engine
(`EventRuleBridge`) rather than introducing a second scheduler. The console is a
standalone `/events` route over an operator-gated `/events/*` API. Tests:
`python/tests/test_events_{core,bus,service,api}.py`. Docs:
`docs/harness/event-system.md`.

## ADR-H154 — Plugins extend Eclipse through its existing systems under a closed manifest, a closed permission vocabulary and enforced isolation

**Decision.** Third-party extensions are first-class plugins, validated against a
versioned manifest (`python/harness/plugins/manifest.py`), granted exactly their
declared permissions and enforced at every call site
(`permissions.py` + `runtime.PluginContext`), driven through a closed lifecycle
state machine (`model.py`) with durable state on `agent-memory.db` (`store.py`)
and an atomic/rollback-safe manager (`manager.py`). A plugin contributes tools,
skills, events, hooks, commands, UI, workers, webhooks and provider descriptors
through a small SDK (`sdk.py`). Contributed tools register on the ONE
`ToolRegistry` (`plug_<id>_<name>`); events publish/subscribe on the ONE run bus
that the Event System ingests; hooks run at the canonical points; effectful
contributed tools reuse the existing effect authorizer. There is no second tool
runtime, event bus, scheduler or agent loop.

**Why.** Eclipse already has the composition surfaces (Tool Registry, Event Bus,
hooks, Evidence engine, approvals). A plugin system that forked any of them would
double the security and observability surface. More importantly, "declared
permissions" are only real if enforced where the resource is touched, and a
manifest is only trustworthy if the runtime is cross-checked against it. Closing
both — the vocabulary and the manifest-vs-runtime agreement — is what makes
installing third-party code a governed act rather than a leap of faith. A closed
lifecycle with an exclusive writer avoids the class of bugs where plugin state
and reality drift across restarts.

**Consequences.** Unknown permissions, malformed SemVer and undeclared/missing
contributions are hard rejections. Elevated permissions (`process.spawn`,
`terminal`, `browser`, `database`, `filesystem.write`) require an operator to
enable. Secrets are encrypted at rest (Fernet, 0600 key file), scoped and never
excluded from logs/telemetry by construction; package integrity is
checksum-verified on load and package file paths are traversal-checked; the only
network path is the controlled HTTP client (timeouts/retries/rate limiting/circuit
breaking + metadata-IP SSRF guard). State is durable, so a restart restores the
enabled set and a plugin that fails to reload becomes FAILED rather than silently
vanishing. Agent reach is opt-in (`allowPluginTools`) and capability-discovered
(`plugin_capabilities`/`plugin_invoke`) so enabled plugins do not bloat every
prompt. `docs/harness/plugin-platform.md` is the operator/author entry point;
`docs/NAVIGATION.md` and `docs/CHANGELOG.md` are updated in the same change.
Untrusted code is additionally isolated in a **separate OS process** (JSON-RPC
with a host-proxied context), so a plugin crash cannot crash Core; OAuth2 token
lifecycle, a SHA-256-verified hosted registry, outbound webhooks, a WebSocket
client and declarative UI view specs are host-owned seams the plugin never
reimplements.

## ADR-H155 - Agent-to-Agent is a registry + typed message bus over the EXISTING execution plane; a delegated task is a normal run

**Decision.** Eclipse's A2A subsystem lives in `python/harness/a2a/` and consists
of a versioned **Agent Registry** (agent behaviour is DATA: capabilities, tools,
permissions, budgets, delegation rights), a typed **AgentEnvelope protocol** with
per-type payload validation and a content-derived idempotency key, a durable
**MessageBus** (publish/consume/acknowledge/reject/dead-letter over
`agent-memory.db`), per-root-run **budgets**, **least-privilege authorization**
with a spawn intersection and an approval gate for trading/external actions, a
**result/finding/conflict** merger, and a **Supervisor + QA** stage. The model-
facing surface is `A2A_TOOLS`; the operator surface is `/a2a/*`.

**Why.** Multi-agent behaviour is where systems most easily fork their own
runtime: a second agent loop, an in-memory queue, a parallel tool registry, a
second database. Eclipse already has exactly ONE of each — `execute_run`, the
`ToolRegistry`, the `EventBus`, the Task runtime (durable tasks + scheduler +
checkpoints) and `agent-memory.db`. The A2A layer therefore creates a durable
**Task** for every delegation and lets the existing `TaskScheduler` dispatch it
through the ordinary run path; messages are rows, not events; the process
`EventBus` only wakes live waiters. This keeps one security surface, one
observability surface and one persistence layer.

**Consequences.** Delegation is non-blocking (returns a task handle); `wait_agent`
is event-driven, never a poll/sleep. Privileges only ever narrow: a child budget,
a spawned agent and a delegated tool set are each the INTERSECTION of the parent's,
and `operator` is never inherited. A capability that touches the real world
(trading, deployment) is approval-gated, so a research agent cannot trade merely by
delegating to one. Findings must carry evidence references; an unbacked or
unverifiable claim is disclosed as **unsupported** with capped confidence, never
promoted to fact. Every message is durable, correlated, idempotent and retryable,
so a crash between publish and consume loses nothing. The A2A tools are registered
on the ONE registry and reachable from `ECLIPSE_AGENT`; the layer is wired from
`boot.py` so the service construction block stays under its size ratchet.
`docs/harness/agent-to-agent.md` is the entry point; `docs/NAVIGATION.md` and
`docs/CHANGELOG.md` are updated in the same change. The Agent Studio graph/live-
execution views (spec §41) are not built yet.

## ADR-H156 - Execution is one substrate: an ExecutionManager routes to DIRECT/CONCURRENT/BACKGROUND/DURABLE over a native durable queue, not a second runtime

**Decision.** Eclipse gains an **Execution Fabric** in `python/harness/fabric/`
that is the common substrate beneath every asynchronous or long-running unit of
work. `ExecutionManager.submit(...)` routes each unit by its type's
`ExecutionPolicy` to one of four modes — `DIRECT` (inline, unpersisted),
`CONCURRENT` (queued, awaited), `BACKGROUND` (queued, fire-and-forget),
`DURABLE` (queued, persisted, idempotent) — over a **native durable queue** on
the ONE `agent-memory.db` connection, served by a **worker pool** (`WorkerManager`)
that claims atomically, heartbeats leases, enforces timeouts, hard-cancels,
retries with backoff + jitter, dead-letters exhausted work, recovers orphaned
jobs and drains on shutdown. Jobs move through a **closed state machine** and
carry correlation/trace/parent/root ids; a `PolicyRegistry` holds the defaults;
`DistributedLockManager` provides TTL'd owner+token locks; and event rules map
selected events to jobs (data, not code in producers).

**Why.** The runtime is a single-process, zero-config, SQLite-backed Python
service (AGENTS.md). Introducing Redis + BullMQ + PostgreSQL (as a generic
"queue layer" brief suggests) would violate the repository's own rules — no
dependency without justification, zero-config must keep working, reuse before
rebuild — and would create a second, disconnected execution plane beside the
already-strong `orchestration` DAG engine, the `tasks` scheduler, the automation
engine, the event system, the plugins and the browser/quant/sandbox runtimes.
The honest gap was not "a queue product" but a **unified routing seam** plus a
durable background worker pool that reuses those capabilities. The Fabric is
that seam: workers never re-implement a capability — an `agent` job calls
`service.run`, a `tool` job calls `ToolRegistry.execute`, `python`/`code` call
the isolated `code.sandbox`, `plugin` calls the plugin manager, `automation`
calls the automation engine, and `notification`/`event` publish on the shared
bus. It persists to the same database as everything else.

**Consequences.** One execution surface, one persistence layer, one security
surface, one observability surface. Priorities are Eclipse's own
(`USER_REQUEST` … `MAINTENANCE`) so bulk ingestion cannot starve an interactive
request. Idempotency keys coalesce duplicate durable submissions. A worker crash
cannot lose durable work: the lease lapses and `recover()` re-queues it. The
manager is the ONE place a new job type is registered (policy + worker), and the
agent tools + `/fabric/*` admin API + `/fabric` console all read the SAME
manager, so they can never disagree. `service.py` is untouched (the layer wires
via `fabric/bootstrap.py` from `boot.py`). If a future deployment genuinely needs
a distributed broker, the `ExecutionManager` boundary is where it would be
swapped in without touching a single agent or tool. `docs/harness/execution-fabric.md`
is the entry point; `docs/NAVIGATION.md` and `docs/CHANGELOG.md` are updated in
the same change.

## ADR-H157 - The agent is measured by running the REAL runtime against versioned, environment-isolated tasks, and every result is per-dimension (never one blended score)

**Decision.** Eclipse gains a first-class **Agent Evaluation System** in
`python/harness/evaluation/`. It executes versioned, environment-isolated tasks
through the real agent runtime — the same `harness.graph.execute_run` tool loop
the product uses — captures the complete trajectory from the runtime's own event
bus, grades it with a pluggable grader engine, aggregates trials with statistics,
persists every result to the ONE `agent-memory.db` connection, compares against
frozen baselines and detects per-dimension regressions. Two invokers share one
runner: a **scripted** offline tier (the real graph with a deterministic scripted
chat model — the model is the only substituted part) and a **live** tier (the
production `AgenticService.run` with a real model). Isolation between concurrent
trials is by `contextvars`, so independent trials run in parallel in one process.
The offline gate is a single step inside the repo's one release gate
(`scripts/test-evals.js`), runs on a private temp database, and is
per-category — never a blended score. An unmeasurable metric renders `UNKNOWN`,
never `0`; a gate fails only on a MEASURED violation.

**Why.** "The tests are green" was the whole claim about agent quality; nothing
measured whether the agent was getting better or worse across task success,
planning, tool selection and arguments, research/citation quality, financial
calculation accuracy, code correctness, memory, safety or hallucination. A single
score would hide the category that always fails behind the one that always
succeeds, and a fake or simplified agent under test would measure the harness
rather than the product. The repo already had the pieces to do this honestly: a
real LangGraph tool loop with a documented model seam (used by its own tests), a
durable event bus, a shared SQLite store, and an established eval-pack pattern
(`research/eval`, `eclipse_memory/eval`, `code/eval`). The evaluation system
reuses all of them and adds only the missing measurement surface — tasks,
environments, trajectory capture, graders, trials, baselines, regression gates,
reporting, mining and the self-improvement verification loop.

**Consequences.** The capability is now measurable end to end: the offline gate
runs 31 labelled tasks across 15 categories through the real runtime and reports
per-category pass counts plus separate dimensions (task success, tool accuracy,
financial/citation/code accuracy, hallucination rate, safety score, cost,
latency, tokens). Graders are pluggable and deterministic where determinism is
possible — financial calculations are independently recomputed, code is actually
executed, state is read from the environment, safety reads the runtime's own
structured refusal codes. Tool arguments, which the runtime's `tool.requested`
event deliberately omits for privacy, are recorded at the `ToolRegistry`
boundary and folded back into the trajectory, so argument accuracy is gradeable
without changing the runtime. A production failure can be mined into a
deduplicated regression candidate and, once its expected behavior is validated,
promoted into the standing suite; the self-improvement loop accepts a change only
when the target improves AND no critical capability regresses. Historical results
are versioned by task, dataset and grader so a change never silently
reinterprets an old score. `docs/harness/agent-evaluation.md` is the entry point;
`docs/NAVIGATION.md` and `docs/CHANGELOG.md` are updated in the same change.

## ADR-H158 - Observability is one vendor-neutral platform that projects the existing event bus; it is fail-open and never a second runtime

**Decision.** Eclipse gains an **Observability Platform** in
`python/harness/observability/`. It is a cross-cutting telemetry layer built on
the standard library only, with an Eclipse-native abstraction
(`ObservabilityHub`, `HookEvent`, `Observer`, `ObservationContext`, `Tracer`,
`MetricsRegistry`, `CostEngine`, `Redactor`, `Sampler`, `BoundedExporter`) and
optional vendor adapters behind one `Exporter` protocol (OTLP/HTTP, Langfuse,
Sentry, JSONL, console, in-memory). It derives telemetry by subscribing **once**
to the existing universal `service.bus` (`RunEventProjector`) and chains the
`model_runtime`'s single observer (`ModelObserverBridge`), rather than adding
instrumentation calls through every subsystem. `install_observability(service)`
is called at the end of `AgenticService.__init__`; `start_observability` /
`stop_observability` run in the FastAPI lifespan; routes are `/observability/*`
(operator-gated).

**Why.** The brief asked for OpenTelemetry + Prometheus + Grafana + Loki + Tempo
+ Langfuse + Sentry. Introducing those dependencies into a **single-process,
zero-config, SQLite-backed** runtime, and re-instrumenting forty subsystems,
would violate the repository's own rules (no unjustified dependencies,
zero-config must keep working, reuse before rebuild, keep files small) and would
create a second, competing telemetry stack beside the existing per-subsystem
`telemetry.py` modules, `event_system/metrics.py`, `fabric/metrics.py` and the
model runtime's own usage/cost/routing accounting. The honest gap was a **unified,
vendor-neutral telemetry layer** that (a) correlates every operation under one
trace, (b) is fail-open so a backend outage cannot break a run, and (c) projects
the event stream Eclipse already emits. OpenTelemetry remains the instrumentation
convention (W3C-shaped ids, `inject`/`extract`); the vendor backends are adapters,
not the core abstraction.

**Consequences.** One ingestion path, one cost engine, one redactor, one export
pipeline. A dead/failing/slow backend only drops and counts telemetry never a
run because every export is bounded, non-blocking, retried and circuit-broken.
Secrets are stripped by the single `Redactor` before any record leaves the
process. Errors, failed runs and anomalies are always sampled. The whole run
trajectory is reconstructable from one trace via
`/observability/traces/{id}/trajectory`. New subsystems join the trace by
publishing on the bus (preferred) or calling `get_hub().emit`/`.span` never by
adding a second stack. `docs/harness/observability.md` is the entry point;
`docs/NAVIGATION.md` and `docs/CHANGELOG.md` are updated in the same change.

## ADR-H159 — Security is one decision path over the existing per-subsystem policies; the floor is immutable and every decision fails closed

**Decision.** Eclipse gains a single Security subsystem at `python/harness/security/`
whose `SecurityGateway` is the ONE authorization path for every privileged
operation. It composes — never replaces — the existing federated controls:
`code/policy.py`, `skills/permissions.py`, `mcp/approvals.py` + `grants.py`,
`browser/policy.py`, `computer/policy.py` + `computer/finance/firewall.py`,
`git/safety.py`, `execution/policy.py`, `terminal/`, `plugins/permissions.py`,
`mcp/ssrf.py`, `observability/redaction.py` and `deps.py`. The gateway owns the
missing central pieces: a **Permission Engine** (resource-scoped globs, never a
global boolean), a **Policy Engine** (LOCKDOWN/SECURE/DEVELOPER/AUTONOMOUS/CUSTOM
profiles, layered system→organization→user→project→agent→task, restrict-only
compose, atomic hot reload that never replaces a known-good policy), a **Risk
Engine** (server-side, ordered by severity), an **Approval Engine** (a typed
broker over the existing single-use `McpApproval` store + `StandingGrant`s), a
**Capability Engine** (issue/validate/delegate/restrict/revoke/expire; delegation
may only reduce authority), a **Security Floor** (immutable hard-deny /
hard-allow / mandatory-approval rules that no profile, skill, plugin, MCP server,
prompt or request field can weaken), a **Network Policy Engine** (default-deny
egress, reusing `mcp/ssrf.py`, DNS-pinned), a **Secrets Manager** (provider
abstraction over env/local, scoped grants, values registered for redaction, never
returned to the model), **session-isolated `SecurityContext`s**, and an
**append-only, hash-chained audit** on the ONE `agent-memory.db`. Authorization
decisions are `ALLOW` / `DENY` / `APPROVAL_REQUIRED` exactly. The initial
migration routes the filesystem and shell capabilities through the gateway at the
existing `code/authorizers.py` seam: the floor and network policy are always
authoritative, policy-driven approvals are deferred to the capability's
established single-use chain, and every evaluation is audited.

**Why.** The brief asked for a unified security architecture covering thirty-five
areas. Reconnaissance showed roughly sixty percent already existed — but
federated, with risk logic duplicated in five modules, redaction in three, no
central risk/policy/network/secrets authority, and no immutable baseline. Building
a parallel stack would have violated `AGENTS.md`'s reuse-before-rebuild rule and
created competing authorities; extending in place without unification would leave
"one authoritative security decision path" unmet and bypassable. A composition
layer that the existing per-subsystem policies delegate into is the only design
that satisfies both the specification's invariants and the repository's own rules.

**Consequences.** Every privileged effect now has one auditable decision path;
the floor protects credentials, keys, the security configuration, system
directories, production infrastructure and financial actions regardless of caller.
Denials and approval-required outcomes fail closed: a missing approval store, an
unreachable secret provider, a broken policy or an internal evaluation error all
yield `DENY`, never a silent allow. Secrets are referenced (`secret://…`), scoped
per consumer/session/task, and stripped from logs, tool output and the audit trail
by the one redactor. Capabilities cannot escalate through delegation. Sessions are
isolated: a capability, secret or workspace from another session is refused.
`docs/harness/security.md` is the architecture entry point; the operator surface
is `/security/*` (operator-gated) proxied by `/api/security/**`. The remaining
capabilities (browser, database, deployment, financial, plugins, MCP, skills) are
migrated in subsequent increments through the same `make_security_authorizer` seam
and the same `AuthorizationRequest` contract. Tests:
`python/tests/test_security_{core,adversarial,failure,concurrency,network_secrets,integration,api}.py`.

## ADR-H160 — Every effectful capability is classified through the gateway; the sandbox is a separate physical boundary; approvals defer to the capability's own chain

**Decision.** The Security subsystem is extended from the initial filesystem/shell
migration to ALL capabilities. `security/classification.py` maps every tool in the
canonical `code/policy.py` effect tuples to `(action, resource, permission)`, so
`build_effect_authorizer` routes browser, computer, git/VCS, execution,
application-runtime, infrastructure/deployment, database, vision, plugin, MCP and
skill effects through the same `SecurityGateway`. The gateway enforces the floor
(hard-deny) and a policy deny as terminal, audits and risk-scores every evaluation,
and **defers approvals to the capability's own established single-use approval
chain** (`defer_policy_approval=True`) so there is exactly one approval and no
double prompt. Environment is resolved from the run context, the deploy action, or
`BLACK_ECLIPSE_ENVIRONMENT`. The physical execution boundary is a separate
abstraction, `security/sandbox.py` (`ExecutionSandbox`), with a hardened
`DockerSandbox`, a `LocalSandbox` over the existing `code/sandbox.py` primitive, and
an `UnavailableSandbox` that fails closed. Secrets gain production providers
(`OsKeychainProvider`, `CliSecretProvider`) and the audit trail an optional
append-only JSONL anchor with an HMAC-signed head. A `SecuritySettingsPanel`
(Settings › Security) is the operator UI.

**Why.** The original ADR left the other capabilities on their own policy modules,
so the spec's invariant "no tool may bypass the gateway" was not yet true and the
unified decision path was advisory for most effects. The choice to *defer* approvals
rather than duplicate them is deliberate: each capability already has a correct,
single-use, digest-bound approval with a working operator UX (MCP approvals, code
actions, git operations, browser/computer ASK). Re-asking at the gateway would
double-prompt and fragment the audit. Hard denies are never deferred, so the
strongest control applies everywhere while the approval surface stays singular. The
sandbox is kept separate from authorization because they answer different questions
— *may this run?* versus *where does it run?* — and conflating them is the classic
mistake the spec warns against.

**Consequences.** Every privileged effect now has one auditable, floor-enforced
decision path; a bypass-audit test fails if any canonical effect tool is
unclassified. The environment actually gates PRODUCTION writes/deploys. Execution
can be placed behind a real container boundary independent of policy. Secrets can
come from the OS keychain or Vault/AWS/1Password via a configured CLI, and the audit
trail can be anchored outside the runtime's writable database. The default remains
zero-config and fail-closed: no Docker, no keychain, and no audit log means the
local backend, honest unavailability, and the in-DB hash chain — never a silent
weakening. `docs/harness/security.md` is updated in the same change; NAVIGATION and
CHANGELOG too.

## ADR-H161 — Identity is verified at the edge and carried as a signed token; tenants are isolated in the security plane; the front door is the authenticator

**Decision.** The runtime no longer trusts a caller-supplied `userId`/`tenantId`.
The Next.js front door authenticates the user, resolves the DB-backed user and
tenant scope, and mints a short-lived (5 min) HS256 JWT with `HARNESS_AUTH_SECRET`
(`src/lib/harness/runtime-identity.ts`). Proxies forward it as
`X-Harness-Identity`; `python/harness/security/identity.py` verifies it with
stdlib only (no new dependency) and yields a verified `Identity`. Precedence: a
valid identity token → the session identity; otherwise loopback / operator secret
→ an operator identity; otherwise anonymous. In multi-tenant mode
(`HARNESS_MULTI_TENANT=1`, or auto-on when the front door requires auth) an
anonymous caller is refused (401). The Security subsystem becomes tenant-aware:
capabilities, secret grants, sessions and audit records carry a `tenantId` and
never cross tenants; the gateway refuses an untenanted request in multi-tenant
mode. Beyond loopback the runtime now refuses to start unless `CRON_SECRET` (and,
in multi-tenant mode, `HARNESS_AUTH_SECRET`) are configured. A per-tenant token
bucket rate-limits the security endpoints.

**Why.** Internet-facing multi-tenancy requires that identity be *authenticated
once, at the edge*, and *proven* to the runtime — not asserted in a body. Reusing
the front door's signing secret keeps one authentication story; stdlib HS256
verification keeps the zero-dependency rule. Scoping capabilities, secrets,
sessions and audit by tenant is the authorization half of tenant isolation and is
the part the security subsystem owns. The remaining half — every run, memory,
task, artifact and database row carrying and enforcing a tenant — is a data-plane
migration across every subsystem's storage, tracked separately; it is NOT claimed
here.

**Consequences.** A stolen/forged token fails signature or expiry; an anonymous
request in multi-tenant mode is refused; a capability or secret granted to tenant
A is inert for tenant B; the audit trail is filterable per tenant; and a
misconfigured public bind without secrets refuses to start. **Boundary:** this
delivers the multi-tenant *security plane* and the identity propagation seam. Full
tenant data isolation (runs, memory, tasks, artifacts, market/JDdS reads, and the
broader proxy rollout of the identity header) is the follow-on data-plane work and
must be completed before a genuine multi-tenant deployment is declared. `/health`
reports `multiTenant` so a deployment can observe the mode.

## ADR-H162 — Tenants are isolated by physical store, the identity header is required on every proxy, and the sandbox is a gate

**Decision.** Three follow-on controls turn the multi-tenant security plane into
enforceable isolation where it can be enforced today. (1) **Physical tenant
stores:** `security/tenant_store.py` resolves a tenant id to its own
`AgentMemoryStore` file under a tenant root
(`.black-eclipse/tenants/<tenant>/agent-memory.db`, `BLACK_ECLIPSE_TENANT_DB_DIR`),
strictly sanitizing the id so a hostile tenant cannot traverse the path. Two
tenants get two databases, so a missing `WHERE` clause cannot leak rows. (2)
**Identity header everywhere:** every `[[...path]]/route.ts` proxy now forwards
`X-Harness-Identity` (via `runtimeIdentityHeaders`), so no route reaches the
runtime without the verified user/tenant. (3) **Sandbox gate:**
`BLACK_ECLIPSE_SANDBOX_REQUIRED` (`1`|`docker`) makes the gateway refuse an
execution action when the required isolation backend is absent, audited as
`security.sandbox.blocked`. A `scripts/security-preflight.js` (`npm run
security:preflight`) fails closed on a network-facing deployment missing
`HARNESS_AUTH_SECRET`/`CRON_SECRET`.

**Why.** The strongest practical isolation for a shared runtime is physical
separation of storage, and it is achievable without threading a tenant through
every existing query. Verifying identity at the edge is worthless if most proxies
drop the header, so the header became universal. An optional-but-enforced sandbox
requirement lets an operator demand container isolation and fail closed when it
is missing, rather than silently running weaker. A deploy-time preflight catches a
missing secret before the first request.

**Consequences.** Tenant runs/sessions/memory can be physically partitioned by
routing them to `TenantStoreRegistry.store_for(tenant)`; until that routing is
wired through the run path (graph/service) the primitive is available but not yet
the default, so **the run path is not yet tenant-partitioned** — this remains the
load-bearing gap. The identity header is now present on all feature proxies; the
explicit `/runs`/`/chat` route still forwards only the front-door-verified
`userId`/`scopeId` and does not yet attach the signed token. The sandbox gate is
opt-in (`BLACK_ECLIPSE_SANDBOX_REQUIRED` unset = current behavior). NAVIGATION and
CHANGELOG are updated in the same change.

## ADR-H160 - The Artifact Center is one catalog over the existing stores; it owns its own tables and a confined content-addressed file store, and every producer registers through one service

**Decision.** Produced files are recorded in a single, durable catalog
(`ArtifactService` + `ArtifactStore`) whose rows live on the ONE
`agent-memory.db` connection, alongside a dedicated, confined,
content-addressed on-disk store under `.black-eclipse/artifacts/`. The catalog is
NOT JDdS (`jdds.db`, market data) and NOT another subsystem's tables. One
service owns the lifecycle (register, version, preview, tag, collect, archive,
restore, delete, purge, reconcile); the REST route group `/artifacts/*`
(operator-gated), the `artifact_*` agent tools, and every producer hook
(`analysis_tools`, the task scheduler) all call that one service. Bytes are never
referenced by a workspace path: the service copies them into the store and returns
an opaque storage key, and the storage layer � not the code policy's workspace
ignore list � enforces confinement (`..`/absolute/symlink escape refused; `*.png`
and `.black-eclipse/**` are legitimate content here).

**Why.** The roadmap's round-2 complaint was that a produced file "never leaves
Eclipse's copy" and nothing serves it. A one-off route per producer would have
duplicated storage, authorization and provenance. One catalog over the existing
connection reuses the harness's durability and the ONE event bus, and gives the
Artifact Center a single place to enforce owner scope, idempotency, lifecycle and
reconciliation.

**Consequences.** Producers depend only on `ArtifactService`; a missing service is
reported honestly (`ARTIFACT_UNAVAILABLE`) rather than silently dropping a file.
Registration is idempotent by key, preview failure never invalidates the original,
and soft-delete/purge are distinct with a shared-reference guard. A bounded
reconciler repairs missing objects on a schedule. New tables live in
`artifacts/store.py` (not `persistence.SCHEMA`), matching the subsystem pattern.
`docs/harness/artifact-center.md` is the architecture entry point; the operator
surface is `/artifacts/*` proxied by `/api/artifacts/**`. Tests:
`python/tests/test_artifacts_{store,security,tools,api}.py` and
`src/lib/harness/artifacts-browser.test.ts`.

## ADR-H162 - Claim verification reaches the delivery seam: an ordinary run's citations are checked against the evidence it actually retrieved, and every web-research run is registered as an evidence-referencing artifact

**Decision.** Two additions close the remaining gap between "the evidence and
verification engine exists" and "it runs before the answer is released":

1. An **evidence release gate** (`research/release_gate.py`) runs at the EXISTING
   answer seam in `graph.execute_run`, beside the code and finance enforcements. It
   is deterministic (no model call): it extracts the final answer's http(s)
   citations and checks each against the URLs the run actually retrieved or
   consulted (the `SourceCollector` provenance the chat Sources panel already
   renders). A cited link with no runtime provenance is disclosed as unverified;
   the verdict is persisted on the run's `research` blob
   (`metadata.citationIntegrity`) and emitted as `evidence.release_gate`. It never
   strips content (suppression would hide a real answer) and is a no-op when the
   answer makes no citations, so casual conversation is not cluttered.
2. A completed **web-research run is registered in the Artifact Center** as a
   durable, evidence-REFERENCING report artifact
   (`artifacts.producers.register_research_report`, invoked best-effort from
   `research/web_engine.py` on completion). The Markdown report names claim
   verdicts, conflicts and an evidence appendix by id, and its `metadata` carries
   the `researchId`, `snapshotId` and evidence ids. It references the evidence
   store; it never duplicates it. Registration is idempotent per
   `(researchId, snapshotId)` and a no-op when the Artifact Center is not
   installed.

**Why.** The evaluation system already GRADED citation support, but the runtime
never ENFORCED it: a model could cite a URL it never retrieved and nothing
detected it before release. The gated financial flow validated its claims; ordinary
runs did not. Separately, a research run's evidence/validation history was
inspectable only inside the research subsystem, not in the one artifact catalog.

**Consequences.** Provider-independent (deterministic; it works with any model, or
none). The `graph.py` size ratchet is re-pinned for the two-line seam. Tests:
`python/tests/test_evidence_release_gate.py`,
`python/tests/test_research_artifact.py`, and two end-to-end cases in
`python/tests/test_graph.py`. Owner docs:
`docs/harness/web-research-engine.md`, `docs/harness/artifact-center.md`.

## ADR-H163 - One cross-subsystem failure layer: a shared taxonomy, stable signatures, a bounded recovery decision and durable incidents, composing — not replacing — the existing subsystems

**Decision.** Add `python/harness/recovery/` as the single layer that answers
"what kind of failure is this, have I seen it before, and what am I permitted to
do about it?". It provides (1) a shared `FailureKind`/`Retryability` vocabulary
and a pure `normalize_failure` that maps every existing subsystem's error codes
(`model_runtime.errors.ErrorClass`, `execution.models.ErrorClass`, the tools
runtime and `orchestration.retry` codes) onto it; (2) stable 16-hex failure
signatures (volatile tokens collapsed) plus a `RecurrenceTracker`; (3) an ordered,
inspectable `select_strategies` policy and a bounded `RecoveryController.decide`
that emits a single `RecoveryDecision`; and (4) durable `RecoveryIncident` /
`RecoveryAttempt` rows on **`eclipse-memory.db`** (migration 26). At boot it
subscribes to the canonical Event System failure vocabulary, so a `tool.failed`
from ANY subsystem is classified and recorded as a durable incident.

**Why.** Eclipse already owned every *piece* of autonomous problem-solving
(provider normalization, execution diagnostics, retry classification, model
fallback, loop detection, task checkpoints, the learning pipeline, verification),
but nothing composed them. A timeout at a tool, a provider and a workflow node had
no shared identity, so recurrence could not be detected and no policy stated what
was permitted. Duplicating those subsystems would violate the repository's
reuse-before-rebuild rule; the missing thing was the composition layer.

**Consequences.** The layer is deliberately NOT a second execution loop: it never
runs a tool, a graph node or a model, and never mutates task state — it decides
and records, and the existing subsystems remain the actors. The policy is
safety-first (never retry a deterministic failure unchanged; never provider-swap
an authentication denial). It is wired in `boot.py` (not `service.py`/`graph.py`,
which are size-ratcheted) and installed idempotently because boot runs once per
lifespan while the tool registry is process-wide. Configurable via
`HARNESS_RECOVERY_*`. The `test_size_budget` ratchet is re-pinned for the
pre-existing in-flight drift in `graph.py`/`service.py`. Tests:
`python/tests/test_recovery_{taxonomy,signature,policy,store,integration,api}.py`
(40 cases, including a live-bus end-to-end capture). Owner doc:
`docs/harness/failure-recovery.md`. Remaining: the UI panel, automatic strategy
execution, and feeding incidents into skill promotion. (App-level ADR series is
unchanged; this is a harness/runtime decision.)

## ADR-H164 - The recovery engine gains the four capabilities it lacked: root-cause diagnosis, bounded automatic execution, unified capability discovery and incident-to-skill promotion — plus a `/recovery` console

**Decision.** Extend `python/harness/recovery/` so the failure layer does the full
loop, not just classify-and-decide:

1. **Root-cause diagnosis** (`diagnosis.py`, `DiagnosisEngine`): a deterministic
   catalog of plausible causes per `FailureKind`, ranked by evidence actually
   gathered, producing a `Diagnosis` that names the selected cause ONLY when the
   evidence is decisive and otherwise lists what is missing. Probes are pluggable
   but the default set is empty (no model fabricates an environmental fact).
2. **Automatic execution** (`executor.py`, `recover_operation`): a bounded async
   loop that runs a caller's operation, consults the controller, honours backoff,
   executes caller-registered repair handlers, and treats a `verify` failure as a
   failure. It records every attempt/outcome on the incident. It is NOT a second
   execution loop: it never runs a tool or graph node, and a strategy with no
   handler is handed back to the caller.
3. **Unified capability discovery** (`discovery.py`, `CapabilityIndex`): one ranked
   index over the Tool/Provider/Skill registries, plus `acquisition_plan` which
   returns approval-flagged steps — it never silently installs or self-grants.
4. **Incident-to-skill promotion** (`learning.py`): a resolved, recurring incident
   becomes an inert `LearningCandidate` through the EXISTING learning store and
   signature scheme; only an operator promotes it. Persisted via migration 27
   (`RecoveryDiagnosis`, idempotent `CREATE TABLE IF NOT EXISTS`).

A standalone **`/recovery` console** (like `/events` and `/fabric`, so it does not
touch the guarded AppTab/sidebar vocabulary) exposes incidents, diagnosis,
attempts, capability discovery and operator-gated promotion.

**Why.** ADR-H163 shipped classification + a decision but stopped at "decide and
record": it could not say *why*, could not act within its budget, could not find an
alternative capability, and could not feed a validated repair back into learning.
These four complete the autonomous loop requested for Eclipse, while keeping the
repository's rules — reuse over rebuild (the learning store, the registries, the
event bus), and no self-granted privilege.

**Consequences.** Migration 27 is idempotent (a separate `RecoveryDiagnosis` table,
not an `ALTER`, so the pre-change-reopen test passes). The executor's retry loop is
bounded by the same `RecoveryBudget`, and within one loop keeps `RETRY` available
(cross-incident recurrence is reflected in the first decision). The new tools are
read-only; promotion and re-diagnosis are operator-gated. Tests: the ten
`test_recovery_*.py` files (64 cases) and `recovery-view.test.ts`. Owner doc:
`docs/harness/failure-recovery.md`.

## ADR-H165 - Autonomy is a pre-committed envelope, not removed approvals: the recovery engine acts unattended only inside a revocable, scoped, expiring envelope, with deterministic probes and a compensation ledger

**Decision.** Add the three pieces that let the recovery engine act WITHOUT a
human per action while staying safe:

1. **The Autonomy Envelope** (`envelope.py`, `AutonomyEnvelope`): an operator sets
   it once — which `ActionClass`es are allowed, under risk / reversibility / cost /
   file-count / network caps, with an optional expiry — and the engine then acts
   unattended inside it. The **default is conservative** (only reversible
   re-run/re-plan/rollback classes), so zero-config behavior is unchanged; effectful
   classes (dependency install, provider/tool substitution, adapter build) require
   the operator to widen it. A global kill switch `HARNESS_AUTONOMY=0` and a
   fail-closed expiry revoke everything. The envelope NARROWS the security layer,
   never widens it — the security floor/permissions still apply on top.
   `recover_operation` consults the envelope before executing any non-retry
   strategy (with a handler); an action outside it is returned to the caller as
   `outside_autonomy_envelope`, never run.
2. **Deterministic diagnosis probes** (`probes.py`): read-only, default-registered
   probes (dependency importability, provider configuration, provider circuit
   health) that return `True`/`False`/`None` — `None` for "unknown", never a guess.
3. **The operation ledger** (`operations.py`, migration 28): idempotency-keyed,
   durable tracking of side-effecting repairs with compensation bookkeeping, so a
   crashed worker reconciles instead of repeating an effect and a failed repair can
   be compensated.

**Why.** The gap between "decides and records" and "acts" is authority, not
capability. Removing approvals would violate the repo's security rules; the correct
mechanism is moving the human decision from per-action to per-envelope, then making
the unattended actions bounded, reversible and auditable.

**Consequences.** The envelope is loaded from config (never written by an agent),
so the engine cannot widen its own authority. The executor's variable-shadowing bug
(`operation` param vs ledger row) was found and fixed by the new tests. New
operator routes: `GET/PUT /recovery/envelope`, `GET /recovery/operations`. The
console gains an "Autonomy & operations" tab. Tests: `test_recovery_{envelope,
probes,operations,executor}.py`. Owner doc: `docs/harness/failure-recovery.md`.
Remaining: wiring the install/build acquisition rungs and automatic compensation
(recorded, caller-performed).

## ADR-H166 - Autonomy becomes durable and coordinated: persisting the envelope, leasing repairs per signature, granting one-off operator approvals, and executing compensating actions

**Decision.** Four additions turn the envelope from an in-memory setting into an
operable, unattended control plane:

1. **The envelope is durable** (migration 29, `AutonomyEnvelope` table): a
   `PUT /recovery/envelope` persists, and `RecoveryService` loads the durable
   override ahead of the config file/default, so autonomy survives a restart.
2. **A per-signature repair lease** (`RecoveryLease`): the executor claims the
   lease for a failure's signature before running a repair handler and releases it
   after, so two workers never repair the same root cause at once (advisory,
   expiring, reclaimable). A held lease returns `repair_lease_held`.
3. **One-off operator approvals** (`RecoveryApproval`): `POST
   /recovery/incidents/{id}/approve` authorizes exactly one strategy for exactly
   one incident, overriding the envelope for that action only — the human fallback
   that keeps the loop usable without widening standing authority.
4. **Compensating actions** (`compensation.py`, `compensate_pending`): registered
   handlers undo a recorded side effect, envelope-gated under the `COMPENSATE`
   action class; operations without a handler or forbidden by the envelope stay
   pending and are reported.

**Why.** The prior envelope could be set but not persisted, could not prevent two
workers from racing the same repair, offered no way to authorize a single
out-of-envelope action, and recorded compensation obligations it could not
discharge. These are the difference between a policy object and a working control
plane.

**Consequences.** The engine still cannot widen its own authority: the durable
envelope is written only by an operator route. Compensation remains caller-driven
by design (the runtime cannot know how to undo an arbitrary external effect). New
store methods (`save_envelope`/`load_envelope_dict`, `acquire_lease`/`release_lease`,
`add_approval`/`has_approval`). Tests: `test_recovery_{compensation,store,executor,
api}.py`. Owner doc: `docs/harness/failure-recovery.md`. Remaining: the install/
build acquisition rungs, evidence-backed diagnosis, multi-agent delegation, and
live console streaming.

## ADR-H167 - Bounded auto-reproduction and hard safety invariants: reproduction makes a diagnosis decisive, and the autonomy engine's trust properties are pinned by adversarial and concurrency tests

**Decision.** Add the last safe, generic rung of the loop and lock the trust
properties:

1. **Bounded auto-reproduction** (`reproduction.py`, `ReproducerRegistry` +
   `reproduce()`): only the caller knows how to safely re-run a failing operation,
   so reproduction is a registry keyed by failure kind. `reproduce()` runs the
   matching reproducer under a hard `asyncio.wait_for` timeout and classifies the
   outcome (reproduced / not / errored); a successful reproduction is recorded as
   evidence and lets the diagnosis select the leading cause on a weaker margin
   (determinism is proven). New operator route `POST /recovery/incidents/{id}/reproduce`.
2. **Adversarial + concurrency tests** pin the invariants that make unattended
   action trustworthy: the default envelope denies effectful classes; the kill
   switch revokes everything; a non-retryable failure is never retried; recovery is
   always bounded; a one-off approval is scoped to exactly its strategy; incident
   messages are length-bounded and signatures are one-way; the repair lease is
   exclusive under thread contention.
3. **Production & operations documentation** in `docs/harness/failure-recovery.md`
   (readiness/degradation, revocation, attack surface, concurrency, CI, and exactly
   what full autonomy still needs).

**Why.** Reproduction was the one generic evidence step the diagnosis engine
lacked, and the safety properties were asserted piecemeal rather than pinned. For an
open-source, single-user tool this is the readiness work: CI (already on
`ubuntu-latest`), a revocable envelope, and tests that fail if a trust property is
ever weakened.

**Consequences.** Reproduction is caller-driven by design (like compensation and
strategy handlers); the runtime registers none by default because it cannot know how
to re-run an arbitrary operation. Remaining for full autonomy: wiring the install/
build acquisition rungs and the delegation roles into the executor. Owner doc:
`docs/harness/failure-recovery.md`. Tests: `test_recovery_{reproduction,safety,
concurrency}.py`.

## ADR-H168 - Research data is verified and versioned above the existing Market Data Gateway; verification is a pure policy engine, datasets are immutable, and no research client re-implements provider routing

**Decision.** Extend the existing market/quant stack into a shared quantitative
research data capability rather than building a second ingestion system:

1. **Verification is a pure engine** (`market/verification.py`): named policies
   (`cached_fast`, `fresh_preferred`, `cross_verified`, `historical_reproducible`,
   `strict_research`) with documented, testable flags. `resolve_policy` raises on
   an unknown name, so a request is never silently downgraded. Cross-source
   comparison is deterministic: disagreeing sources produce a `Conflict` (never an
   average), independence is earned (an unrecorded upstream reports `unknown`, a
   shared upstream is classified distinctly), and only `verified` sets
   `verified=true`.
2. **The Gateway is the one retrieval seam.** Provider routing/quality/provenance
   stay in `MarketDataGateway`; it gains provider pinning (`provider=`) and
   `candidate_providers()` so a caller can deliberately retrieve an INDEPENDENT
   source. The provider capability registry gains intervals, adjustment support,
   a timeliness taxonomy and entitlement.
3. **Datasets are immutable** (`quant/dataset_store.py`): insert-only versions on
   the ONE `agent-memory.db`, a content hash (symbol-order independent) that makes
   a rebuild idempotent, and gzipped artifacts under `.black-eclipse/quant/`.
   New data / changed adjustments fork `vN+1`; the old version is preserved.
4. **One tool surface** (`market/research_tools.py`) wraps the shared Gateway +
   verification + transforms + dataset store; no tool re-implements routing. The
   tools are registered in `market/bootstrap.py` and allowlisted in `agents.py`.

**Why.** Free providers and JDdS can be stale, delayed, incomplete or mutually
inconsistent. The requirement is not "more data" but **defensible** data: prove
where a number came from, whether it was independently confirmed, and reproduce
the exact inputs behind a result. Keeping verification pure and datasets
insert-only makes those properties testable rather than aspirational.

**Consequences.** Verification is only as independent as the configured providers;
when no suitable second source exists `cross_verified` reports `unverified`, not
verified. Provider adapters remain on the TS bridge. The Quant Research screen is
mounted as the `backtest` AppTab (deep link / command palette), not a sidebar
section, matching the Pages/UI-Builder convention. Not yet done: typed Workflow
Graph nodes for the new tools, dataset/version-linked claim verification in the
Evidence Engine, and isolated notebook execution. Owner doc:
`docs/harness/quant-research-data.md`. Tests: `test_market_verification.py`,
`test_quant_transform.py`, `test_quant_dataset_store.py`,
`test_research_data_tools.py`.

## ADR-H169 - Strategy versions are immutable and content-addressed, and the Strategy IR is portable: identity is a sha256 over the canonical IR, and every strategy escapes the UI through a checksummed bundle

**Context.** The Quant Engine persisted strategy "versions" as overwritable
semver rows (`save_strategy` used `INSERT OR REPLACE`) with no content identity
and no portability surface. That made three requirements impossible to honour:
(a) an experiment must reference a strategy state that can never change under it,
(b) two runtimes/the UI must agree that two strategies are the same content, and
(c) a strategy authored in one surface (visual graph, Python lab, AI copilot)
must be usable in another, independent of that surface.

**Decision.**
1. **Content identity** (`quant/schema.py`): `spec_content_hash` is a sha256 over
   the canonical Strategy IR dict (order-independent), and the IR carries an
   explicit `STRATEGY_SCHEMA_VERSION` with a compatibility policy (same major ?
   loadable) and an ordered, lossless migration registry.
2. **Immutable versions** (`quant/store.py`): `QuantStrategyVersion` gains
   `contentHash` + `schemaVersion` columns (idempotent `ALTER` upgrade path). A
   version already referenced by an experiment is frozen: re-saving *different*
   content under it raises `STRATEGY_VERSION_IMMUTABLE` and the caller must bump
   the version; identical content re-saves are a no-op. Editing is always a new
   version. `version_meta` reports the hash, schema and reference count;
   `diff_versions` returns a structural (added/removed/changed) diff.
3. **Portable bundles** (`quant/bundle.py`): a self-describing zip
   (`manifest.json` + `strategy.json` + `README.md`) with format/version id,
   schema version, content hash and provenance. Import is treated as untrusted
   input � compressed/uncompressed size caps, member-count cap, path-traversal
   rejection, no on-disk extraction, schema gating and a hash-mismatch warning �
   and the IR is re-validated through the normal schema path with unknown keys
   preserved.
4. **One surface.** Three agent tools (`export_strategy`, `import_strategy`,
   `diff_strategy_versions`) and matching `/quant/strategies/{id}/export`
   (zip or `?format=json`), `/quant/strategies/import` and
   `/quant/strategies/{id}/diff` routes reuse the SAME store/engine; the IR, not
   the graph, is the source of truth.

**Why.** Immutability is what makes an experiment reproducible: if a version can
silently change after being referenced, every result it produced is
unverifiable. A content hash makes sameness machine-checkable and lets identical
content dedupe. Portability that is a first-class, checksummed artifact keeps a
strategy usable no matter which authoring surface created it.

**Consequences.** Overwriting an *unreferenced* version is still allowed (a
correction), preserving backward compatibility; only referenced versions become
hard-immutable. The migration registry is empty at 1.0.0 (identity) but exists so
a future schema change has one tested home. Python-lab, visual-builder and
AI-copilot authoring still share this same IR + bundle contract. Owner doc:
`docs/quant-engine.md`. Tests: `test_quant_versioning.py`, `test_quant_bundle.py`.

## ADR-H170 - The Visual Strategy Builder is a typed node graph that compiles to the canonical StrategySpec: the registry is the extension seam and the IR stays the single source of truth

**Context.** The spec requires a visual strategy authoring canvas, but also a
strict rule: the visual graph is a *strategy* representation, not a general
workflow graph, and a single universal representation cannot losslessly express
every Python program. Building a canvas before the compile contract exists would
bake the representation into the UI and diverge from the Python lab / AI copilot.

**Decision.**
1. **Typed graph model** (`quant/graph_model.py`): `StrategyGraph` = identity +
   nodes (`id`, `type`, version, config) + edges (`from/fromPort/to/toPort`),
   pydantic-validated so an untrusted UI/agent graph is shape-checked first.
2. **Versioned node registry** (`quant/nodes.py`): each node declares a stable
   `type_id`, its own semver, typed ports (`series`/`number`/`rule`/`any`), a
   config schema + defaults, and a pure `compile(ctx, node, inputs)` that emits an
   IR fragment. Nodes span data/universe, indicators (all catalog entries + the
   multi-output Bollinger/MACD selectors), logic (compare/cross/group/constant),
   trading (entry/exit), sizing, stops/targets and risk limits. Adding a node
   never touches the compiler or the (future) canvas.
3. **Compiler** (`quant/compiler.py`): parse ? resolve types/versions ? validate
   ports/connections/types ? deterministic topological order with cycle detection
   ? compile fragments ? assemble `StrategySpec` ? run the shared
   `validate_strategy`. Emits structured diagnostics (`UNKNOWN_NODE_TYPE`,
   `TYPE_MISMATCH`, `MISSING_INPUT`, `CYCLE_DETECTED`, �) and a source map
   (spec path ? node id). Output is deterministic for equivalent graphs.

**Why.** Compiling to the SAME `StrategySpec` the Python lab and AI copilot
produce means a visual strategy is not a second-class authoring mode: it shares
the immutable-version store, the bundle format, the validator and the entire
backtest/research engine. Keeping the graph deliberately non-Turing-complete and
separate from the future workflow editor prevents the two systems from
entangling.

**Consequences.** The graph is authored **from the chatbot** (the agent composes
a `StrategyGraph` and calls `compile_strategy_graph`/`validate_strategy_graph` —
no dedicated UI, per product direction). Arbitrary Python cannot be represented
as a graph — unsupported constructs stay Python-first, with the graph a faithful
supported subset (no silent loss). Owner doc: `docs/quant-engine.md`. Tests:
`test_quant_graph_compiler.py`.

## ADR-H171 - The Python Strategy Lab runs user strategy code in an isolated worker process and shares the ONE engine for all accounting, so code-first strategies are neither privileged nor divergent

**Context.** The spec requires a serious Python research environment: user-authored
strategy code, a documented SDK, and a *managed* runtime with enforced limits and
no credential/sandbox escape. Two failure modes had to be avoided: (a) treating
`exec`/restricted built-ins as a security boundary, and (b) implementing a second
portfolio/execution accounting path that drifts from the declarative engine.

**Decision.**
1. **SDK** (`quant/sdk.py`): a typed `Strategy` base with lifecycle hooks
   (`initialize`, `on_data`, `on_fill`, `on_order_update`, `on_stop`) and a
   `Context` exposing params, declared indicators, history, position/portfolio
   state, deterministic RNG (`ctx.rng`, seeded) and order intents
   (`buy/sell/close/order`). `run_user_strategy` drives it.
2. **Shared accounting** (`_SdkEngine(BacktestEngine)`): the driver *subclasses*
   the existing engine, overriding only signal evaluation to call user code.
   Fills (next-bar), protective legs, risk engine, portfolio accounting and
   metrics are the SAME code as a declarative backtest � a code strategy is not a
   second-class path and cannot drift financially.
3. **Isolated runtime** (`quant/sdk_worker.py` + `quant/sdk_runtime.py`): the
   source runs in a **separate process** launched with `python -I`, a **scrubbed
   environment** (no PYTHONPATH, no provider keys/credentials), a **wall-clock
   timeout** (killed on overrun), an **output-size cap**, and POSIX CPU/AS limits
   where available. The parent never trusts stdout; it reads a bounded result
   file and *rehydrates* it into a typed `BacktestResult`. Windows relies on the
   timeout + output cap (stated honestly). This is process isolation, not a
   container � a hard FS/network boundary is the harness OS sandbox's job.
4. **Surfaces**: the `run_python_strategy` agent tool (driven from the chatbot) +
   `POST /quant/python/run`, and reference strategies in `quant/examples/`.

**Why.** User code is untrusted and must not run with the harness's authority;
at the same time, a backtest must be reproducible and comparable across authoring
modes. Isolating execution while reusing the engine for accounting satisfies both
without a second ledger.

**Consequences.** Code-first strategies get the immutable-version store, bundle
format and research engines exactly like declarative ones. Multi-file project
authoring and a full syntax-highlighting editor are deferred; the lab's v1 is a
single source module. Capability is advertised `partial` for `pythonStrategies`
(process isolation, not a container). Owner doc: `docs/quant-engine.md`. Tests:
`test_quant_sdk.py`, `test_quant_sdk_runtime.py`.

## ADR-H172 - The AI Strategy Copilot is grounded in deterministic artifacts: it proposes and cites, it never computes results

**Context.** Phase Seven requires a copilot that turns natural language into a
strategy, a research plan and a report, on the SAME infrastructure as manual
strategies. The risk is an LLM that "runs" strategies in prose and invents
metrics.

**Decision.** The copilot's back end is deterministic and the LLM only proposes
and explains:
1. `quant/copilot.py` � `calculate_signals` (the strategy's entry/exit decision
   timeline with reason codes and indicator snapshots, and NO order submission),
   `build_research_plan` (an explicit spec: hypothesis, IS/validation/holdout
   splits, benchmark, declared costs, inferred parameter search, metrics,
   walk-forward, robustness, acceptance criteria, known biases),
   `build_report` (Markdown grounded ONLY in a stored experiment + its artifact),
   and pure helpers to describe rules and to produce validated sizing/stop copies.
2. `quant/copilot_tools.py` registers the spec's tool names (`calculate_signals`,
   `create_research_plan`, `generate_strategy_report`, `generate_entry_exit_rules`,
   `configure_position_sizing`, `configure_stops_and_targets`,
   `get_experiment_status`, `cancel_experiment`, `calculate_performance_metrics`,
   `analyze_trade_log`, `compare_strategies`, `run_parameter_sweep`), all reusing
   the existing store/engine and reusing existing handlers where one exists.
3. Routes `/quant/signals`, `/quant/strategies/{id}/research-plan`,
   `/quant/experiments/{id}/report`. Grounding is carried by the tools themselves
   (their output is a deterministic artifact or an explicit error) — the agent
   system prompt is already at its hard size ceiling, so no prompt text was added.
4. Safety (inherited, not re-implemented): the copilot cannot bypass
   `validate_strategy`, cannot run code outside the isolated worker, cannot
   rewrite a referenced version, and never places live orders.

**Why.** Grounding every copilot claim in a deterministic artifact (signals, a
plan, an experiment report) makes "the AI found a profitable strategy" auditable
or refuted, which is the whole point of the requirement.

**Consequences.** The copilot is not a separate harness � it is prompt guidance
plus grounded tools. Its reports and plans are reproducible artifacts, not model
prose. Owner doc: `docs/quant-engine.md`. Tests: `test_quant_copilot.py`.

## ADR-H173 - The strategy expression DSL, the indicator set and benchmark metrics are extended in the deterministic engine; the chatbot is the only authoring surface (no dedicated strategy UI)

**Context.** Three gaps remained from the strategy spec: the rule DSL was
comparison-only, the indicator library was narrow, and there were no
benchmark-relative metrics. Separately, product direction made clear the whole
feature should be driven from the chatbot, not from dedicated panels.

**Decision.**
1. **Expression DSL** (`strategy.py` + `rules.py`): an `Operand` may be a
   constant, a reference, or a typed `Expr` � arithmetic (`+ - * /`), `min`/`max`,
   unary `neg`/`abs`, and causal `lag`/shift. Evaluation stays safe and causal
   (no `eval`); division by zero / missing operands yield no value, so a
   condition is simply `False` rather than acting on `inf`. Validation recurses
   into expressions (`UNKNOWN_REFERENCE`, `BAD_LAG`).
2. **Indicators** (`indicators.py`): added Stochastic, ADX (+DI/-DI), Donchian,
   Keltner, OBV, MFI, Williams %R and CCI (all causal, catalogued, with node
   registry entries and output selection for the multi-output ones).
3. **Benchmark metrics** (`benchmark.py`): `analyze_against_benchmark` returns
   alpha, beta, correlation, tracking error, information ratio and total/excess
   return from an experiment's equity curve vs a real benchmark series; fewer than
   3 aligned observations returns `available:false` with a reason.
4. **No dedicated strategy UI.** The graph compiler, Python SDK and copilot are
   driven entirely through the chatbot (agent tools). A visual canvas and a
   Python-lab panel were built and then removed per direction; the backend
   contracts are unchanged, so any future UI is a thin client of the same tools.

**Why.** Authoring richness (expressions, indicators) and evaluation depth
(benchmark metrics) belong in the deterministic engine where they are testable
and shared by every path; the chatbot already carries the tool contract, so a
parallel UI would be redundant surface area.

**Consequences.** The rule DSL is now a small safe expression language, still
non-Turing-complete. Benchmark comparison requires fetching the benchmark series
and aligning timestamps; it never fabricates a value when alignment is thin.
Owner doc: `docs/quant-engine.md`. Tests: `test_quant_expressions.py`,
`test_quant_indicators_ext.py`, `test_quant_copilot.py`.

## ADR-H174 - Governance, source inspection and multi-file projects close the strategy lifecycle � but live order routing is structurally refused

**Context.** The strategy spec's remaining backend items were: a governed path
from a reviewed strategy to a deployable one, the paper-trading boundary, source
safety inspection, and multi-file strategy projects � all without a dedicated UI
and without ever enabling live trading.

**Decision.**
1. **Governance** (`store.py`): `QuantStrategyApproval` and
   `QuantStrategyDeployment` tables on the ONE `agent-memory.db`. Approvals move
   `requested ? approved|rejected`. A deployment **requires an approved record**
   for that exact version (`APPROVAL_REQUIRED`) and supports `paper` only;
   `live` raises `LIVE_TRADING_DISABLED` and no path routes an order. A
   deployment is a **record** (`liveExecution: false`), never an execution.
2. **Source inspection** (`ops_tools.inspect_source`): a static AST pass reports
   imports, third-party dependencies, restricted modules and dangerous calls.
   It is explicitly **advisory** � the isolated worker process is the security
   boundary � so it never pretends to be a sandbox.
3. **Multi-file projects**: `run_strategy_source` accepts sibling `extra_files`
   + an `entry` module; the worker adds the project dir to `sys.path`, so a
   strategy can `import` its own helper modules inside the same isolated,
   env-scrubbed, time-limited process.
4. **Static validation depth** (`strategy.py`): `AMBIGUOUS_FILL_TIMING`
   (warning: `fill_at=close` with zero latency can fill on the signal bar) and
   `INDICATOR_TF_UNORDERED` (an indicator timeframe that is neither the primary
   nor a declared confirmation).

**Why.** A strategy lifecycle needs an auditable review gate and a paper boundary
that cannot silently become live. Making `live` a hard, typed refusal (not a flag)
means the safe behavior is the only reachable one; inspection and richer
validation are honesty aids layered on top of real process isolation.

**Consequences.** Paper deployments are bookkeeping records today; wiring them to
a market-data-driven shadow loop is a future step. Container-grade filesystem/
network isolation and pinned per-run dependencies remain the one honest gap
(process isolation only). Owner doc: `docs/quant-engine.md`. Tests:
`test_quant_ops.py`.
