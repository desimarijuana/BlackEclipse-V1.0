---
title: Harness Architecture
status: Current
last-verified: 2026-09-23
---

# Harness Architecture

**Who this is for:** anyone extending BlackEclipse's agentic layer — adding an
agent, a tool, a model provider, or a front-door surface.

The **harness** turns a user request into a grounded, observable, persisted
agent run. The agentic runtime is **Python** (FastAPI + LangChain + LangGraph);
Next.js is a thin front door. This split exists so the agentic side is not
written in TypeScript, while market data stays in its one real home.

## The split

```
Browser / API client
      │  POST /api/harness/runs            (validated, rate-limited)
      ▼
Next.js front door  (src/lib/harness/, src/app/api/harness/)
      │  • validates RunInput
      │  • resolves agent preset + LLM config from the settings vault
      │  • assigns the run id
      │  HTTP  →  http://127.0.0.1:8765/runs
      ▼
Python agent runtime  (python/harness/)
      │  • owned: agents, tools, model providers, events, run persistence
      │  • LangGraph StateGraph: agent ⇄ tools loop
      │  • tool needs JDdS data → HTTP → Next.js data bridge
      ▼
Next.js JDdS bridge  POST /api/harness/data   (read-only)
      └─ Prisma → jdds.db     ← the ONE market-data layer
```

Two boundaries, both deliberate:

- **Next.js → Python on `/runs`** — Next.js owns nothing agentic. It resolves
  what the runtime cannot (vault credentials, run id) and forwards.
- **Python → Next.js on `/api/harness/data`** — the Python tools own their
  contracts (name, schema, permission, risk); the bridge only *reads* JDdS.
  This keeps exactly one financial data path and forbids a second one.

## Python runtime (`python/harness/`)

| Module | Owns |
|---|---|
| `schemas.py` | pydantic wire contracts mirroring the TS types |
| `prompts.py` | system prompts as data (the **Eclipse Agent** prompt lives here) |
| `agents.py` | agent definitions + presets (**authored in Python**) |
| `models.py` | universal provider catalog + LangChain chat-model factory |
| `tools.py` | tool registry: validation, permission, risk, timeout, execute |
| `finance_tools.py` | the Phase-1 JDdS-backed tools (kept for compatibility) |
| `retrieval/` | the **Financial Retrieval Layer**: provider-agnostic hybrid retrieval (Phase 2) |
| `retrieval_tools.py` | the Phase-2 tools; they call the retrieval layer, never a provider |
| `research/` | the **Evidence-Grounded Answering** flow (Phase 4): mandate → coverage → claims → calculations → validation → receipt, plus the bounded web escalation (Phase 5) |
| `skills/` | the **Skill System** (Phase 3): manifests, registry, permissions, execution, learning, evaluation, lifecycle + the shipped skill library |
| `eclipse_memory/` | the **Eclipse-Memory** subsystem (Phase 3-M): dedicated `eclipse-memory.db` for memory, retrieval, corrections, mistakes + the skill/learning tables. `config.py` resolves a **repo-rooted** path (cwd-independent, `ECLIPSE_MEMORY_DB_PATH` override) and reconciles legacy cwd-based stores non-destructively; `intent.py` deterministically classifies explicit save/forget/correct/skill intent |
| `memory_tools.py` | the agent-facing `memory`, `skill_list`, `skill_view`, `skill_invoke` tools |
| `graph.py` | the LangGraph `StateGraph` execution loop |
| `events.py` | per-run event emitter + live bus |
| `persistence.py` | `agent-memory.db` (runs, events, tool execs, memory, skills) + token usage aggregates |
| `service.py` | process-wide store/registry/bus + JDdS data bridge client |
| `main.py` | FastAPI app (`/health`, `/models`, `/agents`, `/runs`, …) |

### Agents and prompts are Python-authoritative

The default agent is **Eclipse Agent** (`id: eclipse-agent`), the platform's
general-purpose financial intelligence identity. Its system prompt lives in
`python/harness/prompts.py` as `ECLIPSE_AGENT_SYSTEM_PROMPT` and is composed
into an `AgentConfig` in `agents.py`. The prompt sets finance-specific standards
for source quality, point-in-time evidence, quantitative comparability, risk,
and capability honesty; the registered tool allowlist remains the actual
execution boundary.

The front door does **not** carry a prompt copy. It sends only `agentId`, and
`resolve_agent()` in `graph.py` resolves the full `AgentConfig` (prompt + tool
allowlist + limits) from the runtime's own presets. `GET /api/harness/agents`
proxies the runtime's `/agents`. This is what keeps one source of truth: updating
the prompt is a one-file change in `prompts.py`.

### The Financial Retrieval Layer (Phase 2)

The agent requests an **objective + data type**, not a provider:

```
tool → Financial Retrieval Layer → planner (task-aware source selection)
     → cache (freshness policy) → parallel/sequential sources
     → normalization → validation → conflict resolution → evidence → tool result
```

`retrieval/` owns this and is the only place that knows a provider exists:

| Module | Owns |
|---|---|
| `contract.py` | the provider-agnostic request/result/evidence models |
| `policies.py` | per-data-type freshness + cache TTL + tier trust ranks |
| `sources.py` | the `RetrievalSource` contract every provider implements |
| `structured.py` | JDdS (vault) + live structured providers (yfinance etc.) + the direct SEC filings source |
| `web.py` | first-class web research (search → rank → retrieve → evidence) |
| `normalize.py` | provider payloads → one `NormalizedFinancialObject` (preserves filing identity) |
| `retry.py` | bounded retry with backoff for transient — never permanent — source failures |
| `cache.py` | TTL cache + in-flight deduplication |
| `parallel.py` | concurrency, per-task timeout, error isolation, cancellation |
| `validate.py` | valid / warning / invalid / unknown (negative earnings stay valid) |
| `conflicts.py` | preserve discrepancies; resolve only with a stated reason |
| `aggregate.py` | `EvidenceSet` keeping evidence kinds distinct |
| `planner.py` | deterministic, explainable source selection |
| `routing.py` | route eligibility + outcome categories (ineligible / not_implemented / unconfigured / provider_failure / no_instrument / no_data / …), so a skip is never reported as an outage |
| `layer.py` | the orchestrator the tools call |

**Source selection is task-aware, not "JDdS first" or "web first".** It is data
in `planner.py`; e.g. a current quote prefers a structured provider, a 5-year
Sharpe prefers structured history, "why did NVDA move" combines market data and
web research, and a historical series never uses web at all. The selected
strategy is recorded on every result (`strategy`) and emitted as an event.

**Precise data is never web-sourced.** `historical_prices`, `macro_series` and
`derived_metric` remove WEB from the plan; when no structured dataset exists the
layer returns `UNAVAILABLE` rather than a web guess.

Tools: `market.get_quote`, `market.get_ohlcv`,
`fundamentals.get_company_profile`, `fundamentals.get_financials`,
`research.search`, `research.retrieve_source`, `research.search_news`,
`macro.get_series` (registered as `*_*` names — the registry allows
`[A-Za-z0-9_]` only).

### Evidence-grounded answering (Phase 4)

Phase 2 retrieval produces provenance, identity, freshness and conflicts. Phase 4
turns a user objective into an explicit set of facts an answer must establish and
gates the final answer against actual evidence. It is a **new package**
`python/harness/research/`, not a second retrieval system: every fact leg is
fetched through the *existing* `FinancialRetrievalLayer`.

```
objective → mandate → per-leg retrieval → coverage → structured claims
          → deterministic validation → research receipt
```

| Module | Owns |
|---|---|
| `mandate.py` | `ResearchMandate` + `FactLeg`; a narrow deterministic classifier (initially `financial_comparison`); optional model-assisted extraction validated against the schema (the model may propose, never author canonical identity) |
| `coverage.py` | per-leg `covered` / `conflicting` / `unavailable` / `unknown` / `not_applicable`; successful retrieval is *not* coverage |
| `claims.py` | `Claim`/`Synthesis`/`ValidationOutcome` + the deterministic validator and prose rendering |
| `calculations.py` | pure-Python period change, CAGR, annualized volatility, max drawdown, Sharpe — with formula/version/input provenance and hard input guards |
| `citations.py` | `Citation`/`ResponseMetadata` assembled only from retrieved evidence (stable interfaces for future workflow nodes) |
| `failures.py` | failure classification (timeout / provider / no-coverage / incomplete / stale / ambiguous / invalid / conflict) |
| `periods.py` | canonical annual/quarter/date/range parsing + matching (no substring-of-digits) |
| `comparability.py` | deterministic identity/comparability gate: blocks a change across a demerger/ticker reuse, unequal durations (9M vs 12M), consolidation basis, metric definition, currency, unit, scale or an unstated restatement, with the exact reason |
| `ids.py` | stable SHA-256 content digests for evidence/calculation identifiers |
| `synthesis.py` | the bounded, tool-less `ModelSynthesizer` (mandate + evidence packet + coverage only) |
| `supersession.py` | source-grounded, cycle-checked restatement chains |
| `eval/` | the versioned, human-labeled semantic-support + escalation sets + runners, and the NVDA labeled regression (`nvda.py`, `dataset_nvda_v1.json`) |
| `budget.py` | the bounded search/fetch/page/time/token budget + exhaustion record |
| `web_facts.py` | span-anchored deterministic extraction/validation of web facts |
| `escalation.py` | bounded structured → primary-web → secondary-web escalation |
| `run.py` | live-chat integration: routes a supported comparison into the gate before the agent graph; renders the keep-going answer |
| `receipt.py` | the bounded `ResearchReceipt` (carries per-leg diagnostics + stop reason + filing identity) |
| `engine.py` | the orchestration over an injected `retrieve` callable |
| `smoke.py` | operator-triggered live network smoke checks (never in the default suite) |

### Global market research (Phase 7)

Eclipse is not US-centric. The market-data path is provider-neutral: a request is
routed by the instrument's verified market/exchange/currency/asset class and data
type, not by a US default.

- **Truthful capability matrix.** `src/lib/harness/capability.ts` composes the
  declared registry with observed universe sizes and recorded health into a
  per-market matrix (recognition / universe / quote / history / fundamentals /
  official filings / web+documents / observed health / live-checked). The
  `get_coverage` and `get_capability_matrix` tools report it, and their text
  explicitly instructs the agent to try other eligible routes rather than stop
  when a market or ticker is missing. Statements are never implied by quotes.
- **Global identity.** The JDdS master stores bare local codes (`2330`, `005930`);
  users type Yahoo-style suffixes (`2330.TW`, `005930.KS`). `splitExchangeSuffix`
  in `markets.ts` maps a curated suffix table to an implied market, and
  `resolveVaultInstrument` queries both forms. An unknown suffix is never guessed.
- **Provider eligibility.** A provider declares eligibility and is SKIPPED when
  ineligible — `SecFilingsSource.eligible` skips SEC for non-US issuers instead
  of attempting it and reporting an outage. The escalation query is market-aware
  (no global "10-K"). A missing credential disables only its route.
- **Documents and language.** The shared fetch transport sends a declared
  email-contact `User-Agent` (SEC fair-access requires it; verified), returns
  JSON/XML/XBRL/plain text as raw text, extracts text-layer PDFs, and reports a
  scanned/image PDF as `unsupported_document` and a JavaScript-only shell as
  `javascript_only` — distinct categories the caller can escalate on. Original
  language is preserved (`WebPage.language`); no silent translation.
- **Health keying.** `sourceHealth` keys each route by `(source, market,
  assetClass)`; a declared target with zero attempts is `unknown`.

The Python research loop, receipt, and per-leg statuses are unchanged; this
phase changes WHICH routes are selected and how their outcomes are reported, not
the evidence contracts.

### Reliability & global-research hardening (Phase 8)

Phase 8 closes the reliability gaps the international runs exposed, without
changing the evidence contracts:

- **Capability tools are reachable.** `get_capability_matrix` and
  `get_research_health` are read-only and in the Eclipse agent allowlist. Missing
  capability data returns a structured error, never a silent fallback to
  `get_coverage`.
- **Timeouts are independent.** A tool's own `timeout_ms` is authoritative; the
  agent's `toolTimeoutMs` is only a ceiling (`tools.effective_timeout_ms`). News
  enrichment has its own bounded budget, so a slow news provider cannot cancel
  statement retrieval or partial-answer rendering. Transient-only retry is
  unchanged (`retry.py`).
- **Route outcomes are distinct.** `retrieval/routing.py` reports ineligible /
  not_implemented / unconfigured / provider_failure / no_instrument / no_data /
  no_matching_period / stale_data / invalid_document, so "we did not try it
  because it does not apply" is never reported as an outage. `capability.ts`
  names each market's real regulator filing system.
- **Capability-specific health.** `sourceHealth` keys
  `(source × market × assetClass × capability × probeKind)` — a healthy quote
  never makes statements/filings look healthy. Zero attempts stays `unknown`;
  fixture probes are labelled and excluded from observed live health.
- **Documents.** The fetch transport distinguishes `too_large`, `empty_response`,
  `javascript_only`, `unsupported_document` and `parse_failure`, preserves
  title/document-id/publication/retrieval metadata, streams to a bounded size,
  and refuses a value-less XBRL taxonomy and a search snippet as evidence.
- **Comparability gate.** `research/comparability.py` deterministically blocks an
  incompatible change (entity/ticker reuse from a demerger, unequal period
  durations, consolidation basis, metric definition, currency, unit, scale,
  unstated restatement) with the exact reason, recorded in the receipt
  (`comparability`) and metadata (`blockedComparisons`). Each verified leg is
  still reported; no misleading percentage is computed.

### Retrieval escalation (Phase 5) and resilient multi-source research (Phase 6)

Structured sources stay the preferred path, but they are no longer the only one.
`retrieval/planner.py` is the explicit, testable source policy; for
`financial_statements` it is:

```
SEC EDGAR (direct filing/XBRL, tier primary, US issuers)
  → JDDS (the structured vault)
  → primary-source web  (SEC/company IR/regulators)
  → reputable secondary web (bounded)
```

The SEC route (`SecFilingsSource` → the `sec_filings` bridge capability → the
existing `sec-edgar` adapter) is independent of the vault and of the search
transport, and routes through the **shared identity gate** so a bare ticker
cannot answer for the wrong issuer. A second web-search provider is
operator-configurable through the settings vault (`SEARCH_API_CONFIG` +
`SEARCH_API_KEY`); the keyless DuckDuckGo HTML provider is always present, and
each provider is a small isolated adapter (`src/lib/web-search.ts`) that can be
disabled or replaced independently. There is still exactly one page-fetch
transport and one market-data bridge.

When structured retrieval is empty, stale, missing a requested period, or lacks
required metadata, `engine.py` escalates each still-unsatisfied leg through the
hierarchy. Escalation is targeted (only the unsatisfied legs), bounded by one
`ResearchBudget`, and every numeric fact must pass `web_facts.validate_fact`: its
page must have been fetched in this run, the cited `sourceSpan` must be a verbatim
quote from that page, the value must appear in the span, the span must not state a
different fiscal period, and metric/period/currency/basis must match the mandate
leg. Page text is untrusted — an instruction in a page is never a fact. A missing
consolidation basis yields a `qualified` leg (the value is present, the basis is
disclosed as unconfirmed), never a hard failure or a silent inference.

**Failure diagnostics.** Every search/fetch attempt records a
`RetrievalDiagnostic` (`src/lib/retrieval-diagnostics.ts`): provider/transport,
normalized status, category (`zero_results` vs `transport_error` / `timeout` /
`blocked` / `http_error` / `content_type_rejected` / `parse_failure` /
`not_configured` / `invalid_request`), HTTP status, latency, timeout state, result
count, bytes, parse outcome and retryability. A JSON source document is accepted
rather than rejected as "not HTML". `retrieval/retry.py` retries only *transient*
outcomes with bounded deterministic backoff; a permanent failure (blocked,
unsupported content type) is never retried. The engine preserves per-leg
retrieval + coverage status + diagnostics and a `stopReason`
(`all_required_legs_resolved` / `budget_exhausted` / `provider_routes_unavailable`
/ `unresolved_facts_remain`) on the receipt. A `research_health` capability
(`get_research_health` tool) probes each route without a research run.

**Keep-going answer.** `run.py` renders every validated fact it has, the source
routes that failed and why, and the exact unresolved facts — a partial run never
collapses to a bare "I can't find it" when other legs were verified. Verified
filing facts carry their document identity (form + filed date + period end) into
the receipt.

**Live chat.** `execute_run` classifies the objective before building the agent
graph. An unambiguous single-entity, two-period comparison is routed into the
gated flow using the run's own `ModelSettings` (no second adapter); everything
else falls through to the Phase 1–3 path unchanged. A gated run persists its
research metadata additively on the run and answers with validated/qualified
claims plus explicit gaps — it is never silently downgraded to an ungated answer.
The chat surface renders citations/coverage via `ResearchEvidencePanel` and can
read the durable receipt at `GET /api/harness/runs/[id]/receipt`.

Persistence is additive: `persistence.py` gains an idempotent `ResearchReceipt`
table in `agent-memory.db` (never `eclipse-memory.db`, never JDdS). Endpoints
`POST /research/mandate`, `POST /research/run`, `GET /research/receipts[/{id}]`
live in `main.py`; the TS front door proxies them, as with every other runtime
route. General/unsupported objectives return `supported=false` and continue on
the existing chat path. Decisions: ADR-H15 … ADR-H19 in
[`decisions.md`](./decisions.md); progress in
[`phase-4-progress.md`](./phase-4-progress.md).

### The Skill System (Phase 3)

A **skill** is a versioned, machine-readable procedure the agent executes
through the *existing* `execute_run` graph — there is no second runtime, tool
registry or agent loop. `python/harness/skills/` owns it:

| Module | Owns |
|---|---|
| `manifest.py` | the pydantic skill manifest + status/risk/category/permission enums, semver |
| `permissions.py` | the **default-deny** permission policy (enforced in code) |
| `store.py` | skill lifecycle persistence in `agent-memory.db` (idempotent DDL) |
| `loader.py` | loading `skill.json` + `SKILL.md` (+ optional `tests/cases.json`) |
| `registry.py` | the single registry: discovery, validation, versions, dependencies |
| `runtime.py` | `SkillExecutionRequest`/`Result` + execution via `execute_run` |
| `learning.py` | run-trace analysis → inert learning candidates; ordinary-chat eligibility + explicit "turn this into a skill" candidates |
| `draft.py` | candidate → unvalidated draft with a real generated procedure + evaluation cases (never auto-enabled) |
| `evaluation.py` | deterministic evaluation + promotion gates |
| `lifecycle.py` | submit-review / approve / reject / rollback |
| `library/` | the shipped skills (research, quality, finance, system) |

Execution composes an `AgentConfig` from the skill: its `SKILL.md` becomes the
system prompt (behind an authoritative runtime preamble), and its `requiredTools`
become the run's tool **allowlist** — the model can never call a tool the skill
did not declare. `SKILL.md` prose is data; the permission check, allowlist and
dependency resolution are enforced in Python code regardless of what the prose
says. Retrieved web/document content is untrusted and can never widen an actor's
grants.

Discovery is deterministic and metadata-only (`discover()`), so full instructions
load **only** for a selected skill — progressive disclosure by construction.
Skill `skill.*` events ride the same `RunEmitter`/bus/persistence as `tool.*`.

Details: [`phase-3-architecture.md`](./phase-3-architecture.md).

### Web research is one shared system

`src/lib/web-research.ts` is the single **page-fetch** implementation and the
diagnostic facade; `src/lib/web-search.ts` holds the ordered, independent
**search providers** (keyless DuckDuckGo HTML plus an operator-configured JSON
API). They back the `web_search`/`web_fetch` bridge capabilities the retrieval
layer calls, and the legacy `search_web` agent tool delegates to them. There is
no second page-fetch system and no second data plane; each search provider is a
small isolated adapter that can be disabled independently.

### Universal model coverage

`models.py` covers "all models" through two mechanisms rather than a branch per
vendor:

1. **Native LangChain integrations** for first-party APIs — Anthropic, Google
   Gemini, Mistral, Groq.
2. **The OpenAI-compatible protocol** for everything else — OpenAI, Ollama, LM
   Studio, OpenRouter, DeepSeek, xAI, Perplexity, Together, Fireworks, and any
   custom base URL + model id.

`PROVIDER_CATALOG` is data: adding a provider is one catalog entry (plus a
provider package in `requirements.txt`). Credentials arrive per run from the TS
vault and are never persisted by the runtime.

### The execution graph

```
START → agent
agent  — model invoked with tools bound
         • no tool calls → END (final answer)
         • tool calls    → tools
tools  — each call validated → permission-checked → timed out → executed
         → agent
agent → … until maxSteps, then MAX_STEPS_EXCEEDED
```

Safety: max steps, per-tool timeout, run timeout, duplicate-call suppression,
read-only enforcement, cooperative cancellation, and exactly one terminal
status. Events (`run.*`, `model.*`, `tool.*`) are emitted and persisted by the
Python runtime.

**Forced final answer.** On the last allowed step the agent node unbinds tools,
appends an in-band instruction to answer now, and strips any residual tool calls.
A tool-looping model (common with local models, which will even hallucinate a
tool that does not exist) therefore produces an answer from the evidence it
gathered instead of `MAX_STEPS_EXCEEDED`. If the forced turn still yields no
text, the run fails honestly rather than reporting a blank "completed".

### Live streaming (SSE)

The runtime streams tokens as the model writes:

```
model.astream → transient `model.delta` events (event bus, NOT persisted)
             → GET /runs/{id}/stream (SSE)
             → GET /api/harness/runs/[id]/stream   (relay proxy)
             → POST /api/harness/chat/stream        (starts the run + relays)
             → chat UI (live status + partial answer)
```

`model.delta` frames are *transient*: they ride the in-process bus to live
subscribers but are never written to the trace (thousands of fragments would
bloat `agent-memory.db`); the assembled message is still persisted by
`model.completed`. A run is started with `background=true` so its stream can be
observed, and the front door sends the terminal `client.final` with the
authoritative answer when the stream ends. If SSE is unavailable the client
falls back to the one-shot `/api/harness/chat` — a run always yields an answer
or an honest error.

### Token accounting

Every `agent` node reads the model response's token usage — LangChain's
`usage_metadata`, or the `response_metadata["token_usage"]`/`["usage"]` block
that OpenAI-compatible and Anthropic endpoints use — and sums
`promptTokens`/`completionTokens`/`totalTokens` onto the run. The per-step counts
also ride on the `model.completed` event.

Providers are not uniform: a local Ollama/LM Studio server commonly omits a usage
block. A missing block records **0**, never an estimate. `GET /usage` therefore
exposes `totals.runsWithUsage` next to the token totals so the UI can distinguish
"no usage reported" from "no activity" — the same honesty rule as UNAVAILABLE
market data.

## Next.js front door (`src/lib/harness/`)

| Module | Role |
|---|---|
| `types.ts` | the small shapes the proxy needs |
| `validation.ts` | untrusted input validation (**no agent config** — that's Python) |
| `run-service.ts` | resolve agent + vault credentials → call the runtime |
| `python-runtime.ts` | lazily spawn + health-check the Python service |
| `python-client.ts` | typed HTTP client for the runtime |
| `data-bridge.ts` | the read-only capability accessor (incl. `sec_filings`, `research_health`, `capability_matrix`, diagnostic-carrying `web_search`/`web_fetch`) |
| `capability.ts` | the truthful per-market capability matrix (recognition vs actual route capability) |
| `agent-presets.ts` | fetches + caches agent presets from the runtime (no local copy) |
| `runtime-config.ts`, `runtime-auth.ts` | package probe list, callback secret/base URL |
| `errors.ts`, `ids.ts` | structured errors, run id |

There is **no** run loop, tool registry or model adapter on the TS side.

### Streaming chat routes

| Route | Role |
|---|---|
| `POST /api/harness/chat/stream` | start a run in the background + relay its SSE stream; emit `client.final` with the answer |
| `GET /api/harness/runs/[id]/stream` | relay the runtime's SSE frames to the browser |
| `GET /runs/{id}/stream` (Python) | the source: replay + live bus, keep-alives, `stream.end` |

The client provider (`src/lib/agent/registry.ts`) parses the SSE frames, maps
them to coarse UI status (`Thinking…`, `Using market_get_quote…`, `Writing…`),
accumulates `model.delta` into the answer bubble, and prefers the authoritative
`client.final` text.

### Conversation checkpoints

A checkpoint is a restorable JSON snapshot of a conversation's turns
(`src/lib/chat/checkpoint-store.ts`), stored under the session folder
(`.black-eclipse/sessions/<chatId>/checkpoints/`, gitignored). The chat state
lives in the browser, so the client sends the snapshot to save and applies a
returned snapshot to restore — the Python runtime stays out of it. Routes:
`/api/chat/checkpoints` (GET list/read, POST create, DELETE). UI:
`src/components/chat/checkpoint-bar.tsx` in both chat surfaces.

### Git workflow

`src/lib/git/service.ts` wraps the repo's git CLI via `execFile` (argument
arrays, never a shell string). It resolves the repo root once (so pathspecs are
correct regardless of the app's cwd), refuses secret-looking staged paths
(`.env`, keys, `*.db`, credentials), never force-pushes, and keeps `push` a
separate explicit action from `commit`. `draftCommitMessage()` builds a subject
from the *actual* staged diff. Routes: `/api/git` (GET status/diff/log/draft;
POST stage/unstage/commit/push). UI: `src/components/screens/git-panel.tsx`,
surfaced as Settings › Git.

## Persistence — a separate database

The Python runtime owns **`agent-memory.db`** (SQLite via stdlib `sqlite3`),
distinct from JDdS (`jdds.db`). Tables: `HarnessRun`, `HarnessEvent`,
`HarnessToolExecution`, `AgentMemory` (user/agent/market facts), `AgentSkill`
(self-improvement). DDL is idempotent, and `_migrate()` adds post-release columns
(e.g. the token columns) to an existing database on open — no manual migration
step. `HarnessRun` carries `promptTokens`/`completionTokens`/`totalTokens`;
`usage_summary()` aggregates them for analytics (`GET /usage`).

## Setup / operations

- `python/requirements.txt` — the runtime stack.
- `scripts/setup-python.js` (`npm run setup:python`) installs it; runs in
  `postinstall`.
- `scripts/doctor.js` repairs it before `dev`/`start`.
- `scripts/test-python.js` runs the pytest suite (wired into `npm test`).
- Env: `HARNESS_PY_URL` / `HARNESS_PY_HOST` / `HARNESS_PY_PORT` (default
  `http://127.0.0.1:8765`), `HARNESS_CALLBACK_URL`, `AGENT_MEMORY_DB_PATH`.
- The runtime is spawned automatically on first use. If it cannot start, agent
  runs return **503 "runtime unavailable"** — never a fake agent.
- **Stable database location.** `eclipse-memory.db` and `agent-memory.db` default
  to the repository root (the dir containing `python/`), not the process cwd;
  `ECLIPSE_MEMORY_DB_PATH` / `AGENT_MEMORY_DB_PATH` override. `GET /health`
  reports the resolved path + a non-secret identity. A legacy cwd-based
  `eclipse-memory.db` is reconciled forward once, non-destructively.
- **Stale-runtime detection.** The spawned Python child outlives a Next.js
  restart (an orphan holding the port), so `ensurePythonRuntime()` compares the
  runtime's `/health` `startedAtMs` against the newest mtime in
  `python/harness/*.py`. If the process predates the code, it is ours and it is
  killed and respawned — otherwise every harness edit would silently keep
  serving old code until the port was cleared by hand.

## Extension points

| To add… | Do this |
|---|---|
| A tool | Define a `ToolDefinition` in `python/harness/`, register it in `register_finance_tools` (or a new `register_*`). Read-only required. |
| A tool that needs JDdS data | Add a capability to `data-bridge.ts` + a `DataCapability` union member; call `ctx.data_bridge.fetch(...)`. |
| A retrieval data type | Add a row to `retrieval/planner.py` (`_PLAN`), `policies.py` (`DEFAULT_FRESHNESS`, `CACHE_TTL_SECONDS`) and the `DataType` literal in `contract.py`. |
| A retrieval provider | Implement `RetrievalSource` in `retrieval/`; register it in `FinancialRetrievalLayer.__init__`. Add its name to the planner's order. |
| A capability the retrieval layer needs | Add a capability to `data-bridge.ts` + the `DataCapability` union + the API route whitelist. |
| An agent | Add a prompt to `python/harness/prompts.py` and an `AgentConfig` to `AGENT_PRESETS` in `python/harness/agents.py` (update `DEFAULT_AGENT_ID` if it should be the default). |
| A model provider | Add a `ProviderSpec` to `PROVIDER_CATALOG`; add its package to `requirements.txt` if it needs a native integration. |
| Durable knowledge | Use `store.remember` / `store.recall` or `store.propose_skill`. |
| A runtime skill | Add a folder under `python/harness/skills/library/<category>/<name>/` with `skill.json` + `SKILL.md` (and optional `tests/cases.json`); it loads at boot via `skills/loader.py`. |
| A skill API surface | Add a proxy route under `src/app/api/skills/` (or `learning/`) and a typed call in `skills-client.ts` (server) / `skills-browser.ts` (UI). |
| A conversational surface | `POST /api/harness/chat` (`chatWithAgent`); pass `history` so follow-ups keep the thread. |
