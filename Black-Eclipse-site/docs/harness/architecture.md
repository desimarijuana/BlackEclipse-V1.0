---
title: Harness Architecture
status: Current
last-verified: 2026-10-02
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
      │  • native finance tool may use JDdS or another planned retrieval source
      ▼
Next.js data bridge  POST /api/harness/data   (read-only)
      └─ Prisma → JDdS plus configured source adapters
```

Two boundaries, both deliberate:

- **Next.js → Python on `/runs`** — Next.js owns nothing agentic. It resolves
  what the runtime cannot (vault credentials, run id) and forwards.
- **Python → Next.js on `/api/harness/data`** — the Python tools own their
  contracts (name, schema, permission, risk); the bridge provides the existing
  JDdS-backed capabilities. JDdS is a source, not an absolute freshness or
  completeness authority. The retrieval layer may select among configured
  sources; user-enabled MCP tools may also be called directly under the normal
  harness tool policy.

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
| `mcp/` | the **MCP integration** (Phase 5A–5C): typed stdio server/effect contract + threat boundary (`config.py`), namespacing/schema validation (`naming.py`), local stdio client over the MCP SDK (`client.py`), and the `ToolRegistry` adapter + lifecycle (`manager.py`). Only selected read-only tools activate. |
| `skills/` | the **Skill System** (Phase 3): manifests, registry, permissions, execution, learning, evaluation, lifecycle + the shipped skill library. `project_skills.py` adds repository-local skill roots (`.black-eclipse/skills/`, `.agents/skills/`) that stay **inert until an operator trusts the root** (`ProjectSkillTrust`, migration 14); precedence is project > profile > bundled, and a project skill runs through the same permission/execution gate (ADR-H59) |
| `eclipse_memory/` | the **Eclipse-Memory** subsystem (Phase 3-M + memory-maturity): dedicated `eclipse-memory.db` for memory, retrieval, corrections, mistakes + the skill/learning tables. `config.py` resolves a **repo-rooted** path (cwd-independent, `ECLIPSE_MEMORY_DB_PATH` override) and reconciles legacy cwd-based stores non-destructively; `intent.py` deterministically classifies explicit save/forget/correct/skill intent; `decision.py` is the **one shared write gate** (`save`/`suggest`/`history_only`/`ignore`) every memory/suggestion/correction/learning write passes through; `policy.py` holds the single learning-mode keys (`memory_mode`, `skill_learning_mode`) with the legacy booleans *derived*, not stored, plus the local privacy keys (`memory_enabled`, `retention_days`, per-category `capture_policy`/`recall_policy`, `memory_in_diagnostics`, `semantic_indexing_enabled`); `conflicts.py` is the authority-aware deterministic contradiction/replacement detector (subject identity/aliases + normalized tokens + reviewed concept axes + polarity/negation + explicit replacement + temporary-instruction exclusion); `normalize.py` holds the synonym/stemming/typo normalization, the `CONCEPT_AXES` polarity model and temporary-instruction detection; `semantic.py` is the optional local, bounded, fail-safe semantic *candidate* layer (default `char-ngram`, no network/model; can only propose a review, never supersede); `transfer.py` is export/import/backup/health/reset; `skill_quality.py` derives skill usefulness metrics from real executions. Retention sweeps run automatically at runtime startup (`main._lifespan` → `AgenticService.run_startup_maintenance` → `EclipseMemoryService.run_retention_maintenance`) and are observable via `MemoryMaintenance` (migration 11); semantic conflict detection is off by default and reports its active mode via `EclipseMemoryService.semantic_status()` |
| `memory_tools.py` | the agent-facing `memory`, `skill_list`, `skill_view`, `skill_invoke`, `session_search`, `session_open` tools, and the M8 provider tools `memory_search_native` / `memory_search_external` / `memory_provider_status` — a `memory` write is a *proposal* re-authorized against the user turn by `eclipse_memory/decision.py`; the session tools and provider tools are read-only |
| `profile.py` (in `eclipse_memory/`) | the compact prompt profile — a deterministic, bounded projection over active memory injected once at run start (`MemoryProfileSnapshot`, migration 12) |
| `session_index.py` | builds the bounded, redacted `SessionMessage` search index of a completed run (never a second copy of the trace) + `build_summary` (a bounded deterministic session summary; searchable, never auto-injected) |
| `learning_review.py` | the bounded in-process post-run learning-review queue (priority-ordered, per-session coalescing, idle-aware; deterministic + optional inert model proposal; never enables a skill) |
| `prompt_segments.py` | immutable prompt segments + a stable `prompt_cache_key` that covers the CONTENT hashes of the reusable (`STATIC_SEGMENTS`) segments (so a prompt edit changes the key), selective bounded skill-manifest injection, the run-scoped `runtime_context_block` date/time segment, and `prompt.plan` observability (`build_prompt_plan`, `build_skill_manifest`, `compare_plans`; `RUN_FROZEN_SEGMENTS` excluded from reuse accounting and the key) |
| `context_budget.py` | the measured per-run history budget: sums the resolved system prompt, advertised tool schemas, per-run blocks and user turn, derives the history allowance from the resolved model's declared window (unknown → conservative ceiling), and keeps `MAX_HISTORY_CHARS` as an absolute cap (`compute_history_budget`) |
| `memory_providers/` | the M8 external-memory-provider layer: `protocol.py` (`MemoryProvider` contract + typed request/response, external `provenance`/`verified=false` defaults), `native.py`, `mcp.py` (read-only-first, L2 write-gated, no automatic writes), `registry.py`, `routing.py` (native-first + external fencing, never promotes), `diagnostics.py` |
| `eclipse_memory/profiles.py` | the M4 named-profile registry (`ProfileRegistry`) + directory projection under `.black-eclipse/profiles/<id>/`; metadata only, READ-ONLY inheritance, no memory content |
| `graph.py` | the LangGraph `StateGraph` execution loop |
| `events.py` | per-run event emitter + live bus |
| `persistence.py` | `agent-memory.db` (runs, events, tool execs, retrieval/receipt records, learning-recurrence ledger) + token usage aggregates |
| `service.py` | process-wide store/registry/bus + JDdS data bridge client |
| `deps.py` | the front door's shared state + authorization seam: the ONE process-wide `AgenticService`, the `require_operator`/`require_mcp_operator` transport/token dependencies, and the identity/tenancy boundary helpers (`identity_boundary`, `deployment_exposure`) |
| `run_lineage.py` | **Phase 1**: run lineage + durable checkpoints + idempotency. Owns the two additive `HarnessRun` columns (`parentRunId`/`workflowId`) and the `RunCheckpoint`/`ToolExecutionIdempotency` tables, bound to the ONE store connection (so ratcheted `persistence.py` did not grow). `save_checkpoint`/`latest_checkpoint`/`mark_tool_executed`/`was_tool_executed`/`set_run_parent`/`list_child_runs` |
| `graph_context.py` | **extraction**: the per-run context blocks (recalled memory, compact profile, skill manifest) and the memory/learning outcome helpers, pure-extracted from `graph.py` to keep it under its size ratchet; re-exported by `graph.py` so callers are unchanged |
| `workflows/` | **Phase 5**: the composable workflow graph. `model.py` (Workflow/WorkflowStep contracts + closed step-kind set + bounds), `validate.py` (cycle / unbounded fan-out / out-of-scope tool / no terminal path — each with a NAMED reason), `store.py` (validated persistence), `compile.py` (compiles onto the EXISTING `execute_run`; a step's tool scope = agent allowlist ∩ step tools, enforced at the same `ToolRegistry.execute(allowed=...)` seam; approval steps reuse the single-use `ApprovalStore`; parallel branches share the run cancel event/cache). Flag-gated (`HARNESS_WORKFLOWS_ENABLED`, default OFF) |
| `eval_gates/` | **Phase 8**: the offline route_health / workflow / resume gates invoked by `scripts/test-evals.js` (the capability-matrix gate lives in TS, `scripts/eval-capability-matrix.ts`) |
| `routers/` | self-contained route groups registered by `main.py` via `app.include_router(...)`, so the front door stays navigable. `mcp.py` owns the MCP catalog/approvals/presets/diagnostics routes; `memory.py` owns all `/eclipse-memory/*` + `/memory-providers/*` routes; `sessions.py` owns sessions/profiles/session-history-search/learning-review; `skills.py` owns the skill lifecycle, project trust, bundles, authoring and learning routes. Shared state comes from `deps.py` (never by importing `main`) |
| `main.py` | FastAPI app (`/health`, `/models`, `/agents`, `/runs`, …). Shared runtime state and operator authorization live in `deps.py`; self-contained route groups are extracted into `routers/` and registered via `app.include_router(...)`. The public surface stays `harness.main:app`. |

### Agents and prompts are Python-authoritative

The default agent is **Eclipse Agent** (`id: eclipse-agent`), the platform's
general-purpose financial intelligence identity. Its system prompt lives in
`python/harness/prompts.py` as `ECLIPSE_AGENT_SYSTEM_PROMPT` and is composed
into an `AgentConfig` in `agents.py`. The prompt sets finance-specific standards
for source quality, point-in-time evidence, quantitative comparability, risk,
and capability honesty; it also carries the **finance-harness contract**: a
`# Market data semantics` block (session state, price/period basis, corporate
actions, point-in-time vs restated, FX, staleness), an `# Inputs and authority`
precedence table with the attached-document rule, an `# Answer contract` (shape,
citation format, numeric conventions, a worked example), and a
`## Runtime awareness` block (bounded steps/timeout, stop rule, truncation,
no redundant retrieval). The registered tool allowlist remains the actual
execution boundary; the run's real date/time is supplied out-of-band by the
`runtime_context` prompt segment, never inside the stable prompt head.

The front door does **not** carry a prompt copy. It sends only `agentId`, and
`resolve_agent()` in `graph.py` resolves the full `AgentConfig` (prompt + tool
allowlist + limits) from the runtime's own presets. `GET /api/harness/agents`
proxies the runtime's `/agents`. This is what keeps one source of truth: updating
the prompt is a one-file change in `prompts.py`. Because a prompt can silently
drift from the allowlist it describes, guard tests (`python/tests/
test_memory_tools.py`) assert over BOTH presets that every tool a prompt names is
in its preset's allowlist and that a prompt never denies a capability its
allowlist contains (ADR-H106).

### The Financial Retrieval Layer (Phase 2)

The agent requests an **objective + data type**, not a mandatory provider:

```
tool → Financial Retrieval Layer → planner (task-aware source selection)
     → cache (freshness policy) → parallel/sequential sources
     → normalization → validation → conflict resolution → evidence → tool result
```

`retrieval/` owns native financial source planning; it can select among the
configured providers for the requested data type. User-enabled MCP tools are
also available as general tools and are not required to implement this contract:

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
| `authority.py` | the ONE ordering table (`AUTHORITY`) + the arbitration decision (`decide_source`); ADR-H115/H116 |
| `planner.py` | deterministic, explainable source selection (adapts `AUTHORITY` into a plan) |
| `routing.py` | route eligibility + outcome categories (ineligible / not_implemented / unconfigured / provider_failure / no_instrument / no_data / …), so a skip is never reported as an outage |
| `layer.py` | the orchestrator the tools call |

**Source selection is task-aware, not "JDdS first" or "web first".** The ordering
is data in `authority.py`; e.g. a current quote prefers a live structured reading
(the vault is a candidate, not the first-and-only — ADR-H115), a 5-year Sharpe
prefers structured history, "why did NVDA move" combines market data and web
research, and a historical series never uses web at all. The price/series/macro
types are **arbitrated**: every eligible candidate runs and a disagreement is
preserved as `CONFLICTING` rather than hidden by the first success. The selected
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
  when a market or ticker is missing. Statements are never implied by quotes. The
  matrix CANNOT assert an impossible fact: `reconcileAxis` represents a
  non-`unknown` observation against an unimplemented level as `matrixInconsistent`
  with a reason. The market set is 34, each with its real ISO currency (CH=CHF,
  KW=KWD, QA=QAR); provider eligibility is DECLARED (`provider-eligibility.ts`)
  rather than inferred. Decision: ADR-H95.
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
- **Health keying.** `sourceHealth` keys each route by
  `(source × market × assetClass × capability × probeKind)`; a declared target with
  zero attempts is `unknown`. The reader is a SUMMARY PARTITION: the compact
  recorded head is the default and the ~1,200-row declared universe is withheld
  until `includeDeclared`/`recordedOnly` is set, so the recorded ledger stays
  readable inside the 24k tool-result bound (ADR-H94). `SourceHealth` carries
  `lastSuccessAt`/`lastFailureAt` per route. A bounded cross-market probe records
  one attempt per (market × implemented capability) into the SAME ledger under the
  SAME canonical key; the manual one-shot works immediately, the recurring
  schedule is OFF by default (`HARNESS_ROUTE_PROBE_ENABLED`). Fixture probes are
  always labelled and never presented as live health. The ledger surface lives in
  `src/lib/harness/health-ledger.ts`.

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
`retrieval/authority.py` is the explicit, testable source policy (the planner
adapts it); for `financial_statements` it is:

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
| `store.py` | compatibility alias: `SkillStore = EclipseMemoryStore` (skill lifecycle lives in `eclipse-memory.db`) |
| `loader.py` | loading `skill.json` + `SKILL.md` (+ optional `tests/cases.json`) |
| `registry.py` | the single registry: discovery, validation, versions, dependencies |
| `runtime.py` | `SkillExecutionRequest`/`Result` + execution via `execute_run`; enforces manifest limits incl. `maxToolCalls` |
| `schema_validation.py` | full JSON Schema validation of skill input/output + schema self-validation |
| `learning.py` | run-trace analysis → inert learning candidates; ordinary-chat eligibility + explicit "turn this into a skill" candidates |
| `draft.py` | candidate → unvalidated draft with a real generated procedure + evaluation cases (never auto-enabled) |
| `evaluation.py` | deterministic evaluation + promotion gates |
| `lifecycle.py` | submit-review / approve / reject / rollback |
| `patches.py` | M2 structured skill patches: JSON-pointer `replace`/`add`/`remove`, allowed-field set, forbidden identity/permission/tool/risk fields, stale-base conflict + never-canary classification |
| `versioning.py` | M2 versioned activation: propose → evaluate → canary → activate, atomic rollback (preserving both versions), automatic rollback triggers, version history |
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

Safety: max steps, per-tool timeout, run timeout, **step-scoped** duplicate-call
suppression (ADR-H90), a **bounded** native tool-result text (ADR-H91),
read-only enforcement, cooperative cancellation, and exactly one terminal status.
Events (`run.*`, `model.*`, `tool.*`) are emitted and persisted by the Python
runtime.

**Duplicate suppression is scoped to one agent step** (ADR-H90). Two identical
`(tool, args)` calls in the SAME turn: the first executes, the second is refused
with `tool.failed`/`TOOL_FORBIDDEN`. A call repeated in a LATER turn executes
again — the guard exists to stop one turn repeating itself, not to block a
legitimate re-issue (next page, re-poll, retry). The retrieval layer still
deduplicates identical data fetches per run via the shared cache, so a cross-turn
re-issue does not multiply upstream calls.

**Tool-result text is bounded at the execution seam** (ADR-H91).
`ToolRegistry.execute` trims a model-facing text result to 24 000 chars with a
non-JSON marker naming shown/total and structured `truncated`/`shown_chars`/
`total_chars` fields; the graph emits `tool.truncated` once per trimmed result.
Under the bound the text is byte-identical; `ToolResult.data` is never bounded.

**Run lineage, checkpoints and resume (Phase 1).** A run now has an identity that
survives a crash. `build_graph` writes a bounded `RunCheckpoint` at every durable
boundary (after each completed agent step, after each tool-result batch, and at
terminal status); the payload is a REFERENCE (step index, counters, pending tool
calls, resolved allowlist, and a capped serialized message tail) — never a second
copy of the event log. Each executed tool call is recorded in
`ToolExecutionIdempotency`, keyed by `sha256(runId, stepIndex, toolCallId)`. A
resume (`POST /runs/{id}/resume`) re-enters at the recorded node, REUSES a
recorded tool result instead of re-running it, and a resume of a run with no
checkpoint is `CHECKPOINT_NOT_FOUND` / of a terminal run is `RESUME_CONFLICT` —
never a silent fresh run. `GET /runs/{id}/lineage` returns the bounded parent
chain + children. Decisions: ADR-H93.

**Forced final answer.** On the last allowed step the agent node unbinds tools,
appends an in-band instruction to answer now, and strips any residual tool calls.
A tool-looping model (common with local models, which will even hallucinate a
tool that does not exist) therefore produces an answer from the evidence it
gathered instead of `MAX_STEPS_EXCEEDED`. If the forced turn still yields no
text, the run fails honestly rather than reporting a blank "completed".

### The composable workflow graph (Phase 5)

Orchestration lives ON TOP of the one execution plane — it does not replace
`execute_run` and does not build a second agent loop, tool registry or model
adapter. A `Workflow` (`python/harness/workflows/`) is a versioned, bounded plan of
`WorkflowStep`s (`agent` | `skill` | `conditional` | `parallel` | `approval` |
`retrieval`). `validate.py` rejects a cycle, an unbounded fan-out, a step
referencing a tool outside its declared scope, and a step with no terminal path —
each with a NAMED reason. `compile.py` invokes the existing `execute_run` per
step; a step's effective tool scope is the INTERSECTION of the workflow agent's
allowlist and the step's declared tools, enforced at the SAME
`ToolRegistry.execute(allowed=...)` seam (a denied call is a structured
`TOOL_FORBIDDEN`). Approval steps reuse the existing single-use `ApprovalStore`.
Parallel branches share the run's cancel event and the shared retrieval cache; the
run ends in EXACTLY ONE terminal status. The step tree is emitted per step on the
existing bus (`workflow.step_started`/`workflow.step_completed`) and shown in the
run explanation.

**Non-goals.** Not a generic harness for arbitrary finance tools — agents must NOT
inherit each other's tools or access, so a step can only NARROW its scope. Not a
visual workflow designer, bot scheduler or agent-builder UI (roadmap Phases 8–9).
The path is flag-gated (`HARNESS_WORKFLOWS_ENABLED`, default OFF); a run with no
`workflowId` behaves exactly as before. Decision: ADR-H96.

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

### Model-aware context budgeting

History is no longer bounded by a hardcoded guess. Before a run, the runtime
measures the **actual request** — the resolved system prompt, the tool schemas
advertised for the run, the per-run blocks (profile, skill manifest, retrieved
memory, dropped-context) and the user turn — then derives the history allowance
from the **resolved model's declared context window** (`ProviderSpec.context_window`
+ `MODEL_CONTEXT_WINDOWS`, via `resolve_context_window`) minus a reserved output
allowance and a margin. `MAX_HISTORY_CHARS` remains an absolute ceiling. The
estimator is the existing `eclipse_memory/profile.py::estimate_tokens` — an
approximation, hence the margin; no tokenizer dependency is added.

An **unknown window stays unknown**: local servers, routers and a custom endpoint
make the budget inert and the bound falls back to the old
`MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS` constants, byte-identical to previous
behaviour. Every surface reports "unknown" rather than a guessed number.

A provider context-length rejection is classified as `CONTEXT_OVERFLOW`
(false-positive guarded against rate-limit/timeout/auth/quota), retried **once**
with half the allowance when it happened on the first model call (so no
side-effecting tool is re-run), and otherwise reported with a specific reason and
remedy. The success path emits `memory.history_bounded` (counts/estimates only)
so a trimmed turn is never silent; the additive `RunResult.context` blob and the
`HarnessRun.context` column carry the same facts for old-row-safe reads.
Decisions: ADR-H63, ADR-H64 in [`decisions.md`](./decisions.md).

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
distinct from JDdS (`jdds.db`) and from the Eclipse-Memory control database
(`eclipse-memory.db`). `agent-memory.db` tables: `HarnessRun`, `HarnessEvent`,
`HarnessToolExecution`, `RetrievalRecord`, `ResearchReceipt`,
`LearningRecurrence`/`LearningRecurrenceRun`, `SessionMessage`(+`SessionMessageFts`),
`ChatSession`, `LearningReview` (with `sessionId`/`profileId`/`priority`/`scheduling`),
plus the legacy `AgentMemory`/`AgentSkill` tables (superseded by Eclipse-Memory;
retained for backward compatibility, no longer the memory/skill source of truth).
`HarnessRun` and `SessionMessage` carry `sessionId`/`profileId`/`projectId`
(additive). Durable memory + the skill lifecycle live in `eclipse-memory.db` (see
the `skills/` and `eclipse_memory/` rows above). `MemoryProfileSnapshot`
(migration 12) lives in `eclipse-memory.db`; migration 13 adds patch/version
metadata to `SkillVersion`. Named profiles are stored at
`.black-eclipse/profiles/PROFILES.json` (a projection, not a second store).
DDL is idempotent, and `_migrate()` adds post-release columns
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

### MCP boundary and source strategy (Phase 5)

MCP is a **user-directed interoperability layer** around the existing Python
`ToolRegistry`. A user may connect MCP servers and use their tools for any
finance workflow; Eclipse does not impose a finance-task allowlist and does not
require external results to go through JDdS or the native research verifier.
JDdS is one source among several and may be stale or incomplete; native retrieval
chooses among configured sources by fit, freshness, coverage and provenance,
while directly connected MCP tools remain available under the user's selection.

An MCP result is attributed to its server/tool and retains upstream provenance
when provided. It is **never** labelled Eclipse-verified unless a separate
verification flow actually checked it. A server's description or result cannot
change system instructions, enable a tool, or authorize a call.

**Implemented (Phase 5A–5C).** A new package `python/harness/mcp/`:

| Module | Owns |
|---|---|
| `config.py` | the typed server contract (id, argv command/args, per-server env allowlist/values, cwd resolution, enabled state, per-tool selection with include/exclude filters, declared effects, coarse `trust` tier, confirmed catalog digest, lifecycle/TLS/capability toggles, startup/catalog/call/output/concurrency budgets) + `${VAR}` connection resolution, secret redaction and owner-restricted config writes. Host execution controls only — not a domain allowlist. |
| `naming.py` | collision-resistant namespacing (`mcp__<server>__<tool>` — a double-underscore boundary; a stable digest only on a genuine sanitization collision), JSON-schema validation before registration, bounded descriptions, effect classification (operator-declared → untrusted MCP annotation → `unknown`). |
| `interpolation.py` | `${VAR}`/`${env:VAR}` + `${workspaceFolder}`/`${userHome}`/`${pathSeparator}` resolution (Milestone 1): one pure function, fail-closed remote rule for `url`/`auth`, literal fallback locally. |
| `screening.py` | static screening of a server entry (Milestone 1): refuse-not-sanitize for shell inline scripts, control operators, download/execute + exfil shapes, and known-IOC package tokens; warn on a plaintext `env` secret. Applied at load, save and spawn. |
| `client.py` | the client over the maintained MCP Python SDK (`mcp`): argv launch with no shell (stdio), Streamable-HTTP and SSE for remote, bounded startup/catalog/call timeouts, serialized session access, cancellation propagation, clean process-tree shutdown, TLS/mTLS controls, structured redacted errors. Non-text content (image/audio) is reported as MIME type + decoded byte size, never an opaque omission. |
| `runtime.py` | `_ServerRuntime` per-server state, the tool descriptor/status dataclasses, and the pure helpers (`_catalog_digest`, `_unsafe_url_reason`, `_allowed_uri`, `effective_resource_schemes`) — pure-extracted from `manager.py` (Phase 6.1). |
| `introspection.py` | the `IntrospectionMixin`: `statuses`/`public_configs`/`summary`/`diagnostics`/`catalog_digest_for` (Phase 6.1 extraction). |
| `oauth_flow.py` | the `OAuthFlowMixin`: `oauth_login`/`oauth_logout` and the device-flow HTTP helpers (Phase 6.1 extraction). |
| `execution.py` | the `ExecutionMixin`: result bounding/rendering, the honest session-expiry policy, and `provider_error_line` (continuation extraction). |
| `verify.py` | the `VerifyMixin`: the operator-triggered credential Verify (one bounded read call; a content-free verdict). ADR-H78. |
| `rediscovery.py` | the `RediscoveryMixin`: handles inbound `list_changed` by rediscovering ONE server through the existing path, under the lock, and emitting `mcp.catalog.changed`. ADR-H81. |
| `circuit.py` | the per-server circuit breaker (CLOSED/OPEN/HALF_OPEN), pure state helpers and named thresholds. ADR-H82. |
| `supply_chain.py` | the spawn-path OSV malware query (fail-closed on a confirmed advisory, fail-open on a network error) with a TTL cache and an injectable fetcher. ADR-H83. |
| `utilities.py` / `lifecycle_mixin.py` | pure extractions (resources/prompts utility tools; the manager keepalive/recycle loop) so `manager.py` stays under its size ratchet. |
| `manager.py` | the `MCPManager` facade: discovery, per-tool selection, catalog-digest confirmation, the `ToolRegistry` adapter, per-call rechecks, the per-run call budget, the circuit-breaker check, bounded/redacted output, and `mcp.server.*` / `mcp.tool.*` events. |

**Lifecycle.** `AgenticService.start_mcp()` (run from the FastAPI lifespan)
connects every **enabled** server, discovers and validates its tools, then
registers only **selected**, effect-permitted tools into the ONE `ToolRegistry`.
`stop_mcp()` terminates every subprocess cleanly on shutdown and unregisters only
the names the manager owns (native tools are never touched). `/health` reports
configured/connected/registered counts (never secrets). A `test_server` probe
always tears its temporary child down (success, failure or cancellation).

**Resilience (Phase 6 M2).** A failed initial connect is retried with a jittered
exponential budget and, if it never connects, reaches a terminal state reported
with the attempt count. A call arriving at a failed/closed/lazy server triggers
one bounded reconnect (`manager._reconnect_on_call`) that re-checks selection,
catalog digest and effect before re-registering. A mid-call session expiry
classifies honestly: a **read** is replayed exactly once after a reconnect; a
**write/external_action** is never replayed and returns an explicit
`outcomeUncertain` result. One manager lifecycle task drives keepalive
(`keepalive_interval`) and stdio recycle (`idle_timeout_seconds` /
`max_lifetime_seconds`, only when no call is in flight). A `lazy` server
registers its tools from an on-disk cache keyed by a fingerprint of the
connection config (`mcp/schema_cache.py`) and spawns on first call; a missing or
stale entry falls back to eager. No MCP child outlives Eclipse: on POSIX a single
stdlib-only supervisor (`mcp/orphan_supervisor.py`) reaps registered process
groups on parent death via pipe EOF; on Windows the SDK's Job Object
(`KILL_ON_JOB_CLOSE`) already does. ADR-H68.

**Default-agent reachability.** The Eclipse agent sets `allowMcpTools: true`,
which expands its run allowlist to include the MCP tools **currently registered**
in the registry (`mcp_*`). Registration already requires an enabled server, an
explicit per-tool selection and a permitted effect, so this cannot surface a
merely discovered tool. Custom agents and skills do **not** set the flag and keep
their exact restricted allowlists.

**Discovery is not activation.** `enabled` defaults to False, `selected_tools`
defaults to empty, and only `read`-effect tools are activatable without the
effectful-approval path; a `write` / `external_action` / `unknown` tool needs the
operator to enable that effect class and a matching per-call approval (5G).
Further, an effect is trusted only from an **operator declaration**
(`tool_effects`) or from the operator confirming the server's `catalogDigest`: a
server's own `readOnlyHint` is untrusted and, on its own, leaves the tool
disabled. A changed catalog (tool set / description / schema) produces a new
digest and invalidates prior confirmation until the operator re-confirms.

**Continuation hardening (2026-09-30).** Four further properties ride the same
boundary: (1) an inbound `list_changed` notification (tools, resources OR prompts)
triggers a refresh of that ONE server's listing through the existing path; a
changed tool catalog re-engages the confirmation gate so it cannot keep a tool
active, a changed resource/prompt listing replaces the connect-time snapshot the
utility tools serve, and a content-free `mcp.catalog.changed` event fires
(ADR-H81) — but only when the digest actually moved: a `list_changed` that
announces no real change is re-discovered and produces NO event, so a server that
fires the notification gratuitously cannot spam the operator with "catalog
changed" prompts to re-confirm an identical catalog (ADR-H87). (2) A per-server
**circuit breaker** stops futile calls to a server that connects but fails every
call: only transport failures count (never a denied approval, a caller-side
error, a budget/breaker refusal or a cancellation); an open breaker refuses
immediately and honestly, re-probes once after a cooldown, and has an operator
reset (ADR-H82). (3) A **spawn-path OSV check** refuses a package with a confirmed
malware advisory and allows one on a network error, always stating which
happened, with a TTL cache (ADR-H83). (4) A **sampling model allowlist** bounds
which model a server may request; an over-long assembled tool name is clamped to
64 chars with a stable digest (ADR-H84).

**Trust tier (Phase 6 M1).** `trust` is `full` (default) or `untrusted`
(fail-closed: any unrecognized value is untrusted). An untrusted server requires
a per-call approval for **every** non-read call regardless of `enabled_effects`,
and only an operator-declared effect can activate its tools — its own annotations
never do. This is strictly additive to the operator-declared-effect rule.

**Config contract, screening, sharing (Phase 6 M1).** `${VAR}`/`${env:VAR}` and
`${workspaceFolder}`/`${userHome}`/`${pathSeparator}` are resolved from the
process environment at load/spawn (`mcp/interpolation.py`); a remote `url`/`auth`
with an unresolved reference **refuses the connect by name** (never sends a
literal placeholder), while local stdio values keep the literal. `selected_tools`
accepts the legacy exact list or `{include, exclude}` fnmatch globs (include wins;
empty include selects nothing). A static screen (`mcp/screening.py`) refuses a
shell-interpreter inline script, shell control operators, download/execute and
exfil shapes, and known-IOC package tokens — at load, at save and at spawn — and
warns on a plaintext `env` secret. Eclipse tool names are
`mcp__<server>__<tool>` (double underscore). ADR-H67.

**Config round-trip: a save never silently widens authority (Phase 6.1).**
`upsert_mcp_config` merges from the incoming model's `model_fields_set`:
**absent means preserve; explicitly present means replace** — including an
explicit `null`/`false`/`{}`/`[]` for clearing. A partial save therefore cannot
reset a field it did not mention, so `trust`, `enabled_effects`, `tool_effects`,
`data_source_tools`, `confirmed_catalog_digest` and `selected_tools` are
preserved unless a caller deliberately sends them. `env` keeps its write-only
merge. `install_mcp_integration` is create-if-absent (re-installing never resets
an operator's changes). The settings UI is a full-fidelity editor: it reaches
every field (`trust`, include/exclude filters, per-tool effects, native data
sources, `tools.resources/prompts`, `resource_schemes`, lazy/keepalive/idle/
lifetime, TLS/mTLS, limits, SSE transport, OAuth sign-in) and the
view↔draft↔input mapping is the pure module `src/lib/harness/mcp-draft.ts`.
`public_dict()` emits the raw operator-set bounds so the wire is lossless;
`public_configs()` exposes the capability toggles as `capabilityToggles` (the
`tools` key is the discovered-tool array). ADR-H74. `resource_schemes` narrows
the resource URI schemes a server may read; the global allowlist is a hard
ceiling and narrowing can only ever remove a scheme. A non-text MCP result
reports MIME type and decoded byte size rather than an opaque omission.

**Execution stays authoritative.** Every MCP call enters through
`ToolRegistry.execute`, so argument validation (pydantic), the agent allowlist,
read-only permission, timeout and persistence are enforced exactly as for native
tools. The adapter additionally re-checks, at call time, that the server is still
enabled and connected, the tool is still selected/activatable, and the effect is
permitted. Task cancellation propagates to the MCP request; no retries are issued
for a call that may have side effects. Output is bounded to the configured size,
marked truncated when cut, and redacted — source identity (`serverId`, original
`tool`) and upstream `structuredContent` are retained.

**Trust boundary.** Launch uses an argv list with no shell. Only an explicit
per-server env allowlist/values reach the child — never the Eclipse process
environment, settings vault, model credentials or callback token. A relative
cwd resolves against the repository root, so it cannot be redirected by the
launch cwd. Server descriptions and results are untrusted data and can never
widen tools, permissions or instructions.

**Configuration & credentials.** `<repo root>/mcp-servers.json` (override:
`HARNESS_MCP_CONFIG`); a missing file means MCP is simply not configured.
Discovered env VALUES are persisted in that file because the secure settings
vault is a TypeScript/Prisma store this Python process cannot read and the SDK
needs the value to spawn the child. The file is gitignored and written
owner-only (0600 where the OS supports it); the API returns env KEY names only,
and values are redacted from every diagnostic/event/result (see ADR-H40 for the
vault-integration limitation and the planned secret-reference resolution).

**Catalog selection (Phase 5E).** `python/harness/routers/mcp.py` (registered by
`main.py`) exposes the catalog over the runtime API — `GET /mcp/servers`, `POST /mcp/servers`,
`POST /mcp/servers/test`, `DELETE /mcp/servers/{id}`, `POST /mcp/reload`,
`POST /mcp/servers/{id}/confirm` — and the TS front door proxies them at
`/api/harness/mcp/*` (`src/lib/harness/mcp-client.ts`,
`src/lib/harness/mcp-types.ts`). The Settings UI
(`src/components/screens/mcp-settings.tsx`, section `mcp`) lets an operator
add / test / enable / disable / remove a server, review its discovered tools and
their effect classes, select the read-only tools to activate, and confirm a
changed catalog. A save reloads the manager in place: only the MCP tools it
previously registered are dropped and re-registered, so a change takes effect
without a runtime restart and native tools are untouched. Responses are
secret-free — env VALUES are write-only and the API returns only env KEY names.
Each server also has a versioned `catalogDigest` (identity + effect + schema) so
a changed tool set is reviewable. This is not a finance-domain allowlist: the
user chooses which servers and tools to connect.

**Authorization.** MCP mutations require proof of authorization — the request
must originate from loopback (the front door / local operator) **or** present the
runtime secret (`X-Harness-Operator` / `Bearer`), never a caller-supplied JSON
boolean. As of Phase 6 M1 the previously-open Python MCP **read** routes
(`GET /mcp/servers`, `GET /mcp/approvals`, `GET /mcp/integrations`,
`GET /mcp/workflows`, `POST /mcp/diagnostics`) carry the same
`require_mcp_operator` dependency, because the TS front door already forwards the
operator token — so a directly reachable Python runtime does not expose the
configured subprocess surface to an unauthenticated caller. Tests:
`test_mcp_api.py` (`test_read_routes_refuse_a_non_operator`).

The SAME rule now guards **every** memory/skill mutation endpoint (memory
create/update/archive/review, corrections, policies, suggestion accept/dismiss,
skill author/enable/disable/deprecate/rollback, learning from-run / generate-draft
/ reject, and skill-draft submit/approve/reject). Each takes the
`require_operator` FastAPI dependency (`main.py`), which is transport/token only;
the body `operator` boolean is read afterward and can never by itself authorize.
Previously these endpoints trusted the body boolean, so a directly reachable
runtime — or a crafted proxied payload — could self-authorize; the Next.js clients
now forward the runtime secret as `X-Harness-Operator` so the front door's own
authorization is what reaches Python. Tests: `test_memory_api_auth.py`,
`test_mcp_api.py`.

**Transports (Phase 5D).** A server is `stdio` (local subprocess, default),
`http` (remote Streamable-HTTP) or `sse` (remote SSE). `MCPServerConfig.transport`
selects it; a remote transport requires a `url` and may carry
`auth: {kind: "header"|"query"|"oauth", name, prefix, secretRef}` resolved from
the vault at connect time. All transports share the SAME connection lifecycle,
discovery, effect/approval gating, output bounding and redaction — only the
stream source differs (`client._transport`). A remote URL is checked by
`harness/mcp/ssrf.py` (https-only, loopback http allowed; private addresses and
embedded credentials refused) BEFORE any outbound connection. TLS controls
(`ssl_verify: true|false|CA-path`, `client_cert`/`client_key` for mTLS) are
honored. A hand-typed header/query `auth` is the shipped path; the full OAuth
authorization-code + device flow and the redirect/origin policy remain (Phase 6
M3).

**Finance product layer (presets, workflows, diagnostics).** MCP is presented to
an investor as finance jobs, not servers. `python/harness/mcp/presets.py` is pure
data: finance **integrations** (Sheets/Excel, filings, web search, calendar,
cloud docs, Canva/Figma/Office decks, Notion — each with plain-language setup,
verification/community flags, and read/write tool-name hints) and named
**workflows** (Import Portfolio, Review Portfolio Risk, Prepare Earnings Brief,
Compare Companies, Analyze Trade Journal, Create Investment Memo, Export
Portfolio Report — each with steps, per-step integration, native-vs-MCP, and
approval steps). `python/harness/mcp/diagnostics.py` produces actionable setup
diagnostics (command/Node/npx/Python availability, vault secret references,
endpoint safety + reachability, connection, discovery, selection, and a writable
temp dir) with a `recovery` step each. Runtime routes `/mcp/integrations`,
`/mcp/workflows`, `/mcp/diagnostics`; TS proxies under `/api/harness/mcp/` and a
workflow wizard + diagnostics panel in Settings › MCP Servers. **Every MCP
result carries provenance** (`verification: external`, `eclipseVerified: false`,
source, `retrievedAt`) and is labelled external in its text; native JDdS/portfolio
data stays authoritative. An effectful approval records a plain-language
`actionSummary`, `affectedData` and `risk`. Decisions: ADR-H43.

**Source independence.** MCP results are never routed through JDdS or the native
research verifier and are never labelled Eclipse-verified; they are attributed to
their server/tool. The default prompt tells the agent that JDdS is one fallible
source; to try other eligible configured sources and selected MCP tools before
concluding evidence is unavailable. MCP-aware source planning is **wired into the
native retrieval layer**: an operator-declared MCP data tool (a server's
`data_source_tools` map) becomes a `RetrievalSource` via
`manager.mcp_sources()`, reaches the layer through `ToolContext.mcp_manager`, and
`plan_retrieval(additional_sources=...)` considers it after the native structured
sources but before generic web. The planner primitive
(`mcp/mcp_retrieval.py`) keeps three distinct freshness states
(`fresh`/`stale`/`missing`, plus `failed`) and **preserves a conflict** rather
than silently choosing; provenance is always `secondary`/`eclipseVerified=false`
and a JDdS result is never silently upgraded. A generic MCP tool that is not
declared stays directly callable by the model and is never withheld. Remote
HTTP/OAuth/SSE/TLS (`5D`), resources/prompts (`5I`), sampling/elicitation,
Eclipse-as-MCP-server (`5H`) and the finance preset/install/audit surface (`5F`)
are **implemented**; subscriptions remain a documented non-goal (see the progress
doc and ADR-H67–H73).

### MCP secret references and effectful approvals (Phase 5 extras)

**Vault-backed secret references.** A server can reference a NAMED secret instead
of storing a value: `secret_refs: { API_TOKEN: "my_server_token" }`. The secret
is stored ENCRYPTED in JDDS (`SystemConfig.key = 'mcp_secrets_v1'`, AES-256-GCM
via `connectors/secrets`) and exposed only as names/masked hints
(`/api/harness/mcp/secrets`). The Python runtime resolves the value at spawn over
the authenticated, read-only data bridge (`mcp_secret_resolve`) — a
server-to-server path. The value never reaches a browser, the model, an event, a
log, or a run trace; it is added to the connection's in-memory redaction set so a
server cannot echo it back either. Inline `env` values remain supported but are
the legacy/plaintext path; `secret_refs` is preferred.

**Effectful-tool approvals (5G).** A tool whose effect is `write` or
`external_action` is not run on the model's say-so. Two gates apply:
1. the operator must enable that effect class for the server (`enabled_effects`,
   default `["read"]`); and
2. every call must match an APPROVED, unexpired approval bound to
   `(serverId, tool, argsDigest)`, where the digest is the canonicalized
   validated arguments. A changed payload requires a new approval; a denial is
   terminal for that digest; `unknown` effect is never approvable.

Enforcement is in the ONE `ToolRegistry`: a non-read `ToolDefinition` executes
only when the run's `ToolContext.authorize_effect` authorizer approves the exact
call. With no authorizer wired, every non-read tool is refused (the prior safe
default). When a call is unapproved, the runtime records a PENDING request and
refuses it, emitting `mcp.tool.approval_required`; the operator decides in
Settings › MCP Servers (`/api/harness/mcp/approvals`). Approvals live in
`agent-memory.db` (`McpApproval`) and hold no secret material.

**An approval is single-use** (ADR-H92). A successful authorization atomically
CLAIMS the approval (guarded `UPDATE ... WHERE status='approved'` + rowcount
check) and moves it to a terminal `consumed` state with a `usedAt` stamp. One
operator decision authorizes exactly ONE call; a second identical call is refused
and produces a fresh PENDING request. Because one effectful call is authorized at
two seams (the registry gate and the MCP manager's `_execute` re-assert), the
first claim records the authorized digest on the shared `ToolContext` for that
call-scope so the second seam does not consume again; a new call starts a new
scope. `consumed` and `usedAt` ride the whole round-trip (the row, `_row()`,
`GET /mcp/approvals`, `MCPApprovalView`, and the approvals UI).

| To add… | Do this |
|---|---|
| A tool | Define a `ToolDefinition` in `python/harness/`, register it in `register_finance_tools` (or a new `register_*`). Read-only required. |
| A tool that needs JDdS data | Add a capability to `data-bridge.ts` + a `DataCapability` union member; call `ctx.data_bridge.fetch(...)`. |
| A retrieval data type | Add one row to `retrieval/authority.py` (`AUTHORITY`, a `DataTypeAuthority`), `policies.py` (`DEFAULT_FRESHNESS`, `CACHE_TTL_SECONDS`) and the `DataType` literal in `contract.py`. The authority is the ONE ordering table (ADR-H115). |
| A retrieval provider | Implement `RetrievalSource` in `retrieval/`; register it in `FinancialRetrievalLayer.__init__`. Add its name to the planner's order. |
| A capability the retrieval layer needs | Add a capability to `data-bridge.ts` + the `DataCapability` union + the API route whitelist. |
| An agent | Add a prompt to `python/harness/prompts.py` and an `AgentConfig` to `AGENT_PRESETS` in `python/harness/agents.py` (update `DEFAULT_AGENT_ID` if it should be the default). |
| A model provider | Add a `ProviderSpec` to `PROVIDER_CATALOG`; add its package to `requirements.txt` if it needs a native integration. |
| A local MCP server | Add an entry to `<repo root>/mcp-servers.json` (see `harness/mcp/config.py`): `id`, `command`, `args`, optional `env`/`env_allowlist`/`secret_refs`/`cwd`, `enabled: true`, and the `selected_tools` include list. Only read-only tools activate in this slice. Or use Settings › MCP Servers (`/api/harness/mcp/*`). A ready-to-edit set (Notion, Google Sheets, Excel, Tavily/Brave search, filesystem, Yahoo Finance, memory) is in `mcp-servers.example.json`. |
| Durable knowledge | Use `store.remember` / `store.recall` or `store.propose_skill`. |
| A runtime skill | Add a folder under `python/harness/skills/library/<category>/<name>/` with `skill.json` + `SKILL.md` (and optional `tests/cases.json`); it loads at boot via `skills/loader.py`. |
| A skill API surface | Add a proxy route under `src/app/api/skills/` (or `learning/`) and a typed call in `skills-client.ts` (server) / `skills-browser.ts` (UI). |
| A conversational surface | `POST /api/harness/chat` (`chatWithAgent`); pass `history` so follow-ups keep the thread. |
