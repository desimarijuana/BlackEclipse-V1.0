---
title: Vibe-Trading — External Implementation Analysis and Gap Register
status: Current
last-verified: 2026-11-20
---

# Vibe-Trading — External Implementation Analysis and Gap Register

**What this doc is.** A read-only analysis of the external project
`HKUDS/Vibe-Trading` (v0.1.19, commit `1dbe5d5`), written to answer one
question: *which capabilities does that codebase have that Eclipse lacks or is
behind on, and what exact Eclipse contract would each one change?*

**What this doc is not.** It is not a plan to adopt Vibe-Trading's
architecture. Three of its central choices are deliberately rejected here (see
[Non-goals](#non-goals)). It is also not a benchmark: every number below is a
static measurement of source, not a runtime measurement.

**Provenance.** Measured from a clone at
`%TEMP%\opencode\vibe-trading`. Inventory produced by AST scripts
(`vibe-tools-inventory.py`, `docsweep.py`) and `Get-Content`/`Select-String`
over the tree. Re-measure before citing these numbers after the external repo
moves.

---

## 1. Scale, measured

| Area | Files | LOC |
|---|---:|---:|
| `agent/src` (33 packages) | 2,438 | 472,123 |
| `agent/backtest` | 95 | 29,105 |
| `agent/cli` | 45 | 12,736 |
| `agent/evals` | 43 | 7,630 |
| Python tests | 1,116 files | — |

Eclipse for comparison: `python/harness` 446,359 LOC, 997 test files,
77 routers, 471 API routes, 33 screen directories. Vibe-Trading is smaller in
Python but broader in *domain surface*; Eclipse is larger in product surface.

### Package inventory (Vibe-Trading)

| Package | Files | LOC | Purpose |
|---|---:|---:|---|
| `tools` | 126 | 44,018 | 126 `BaseTool` classes |
| `factors` | 496 | 26,195 | Alpha Zoo, 5 zoos, 460 alphas |
| `trading` | 102 | 19,077 | 19 broker connectors |
| `channels` | 41 | 19,086 | 19 IM platforms + credential probes |
| `backtest` | 95 | 29,105 | 15 market engines, 45 loaders, 6 optimizers |
| `quantlib` | 28 | 16,370 | 22 named math modules |
| `cli` | 45 | 12,736 | Interactive REPL, slash commands, onboarding |
| `api` | 34 | 9,851 | 32 route modules |
| `live` | 28 | 8,336 | Mandate enforcement + kill switch |
| `agent` | 24 | 7,332 | ReAct loop + 5-layer context |
| `providers` | 15 | 5,564 | Multi-provider LLM layer |
| `data_gateway` | 28 | 4,738 | 38 sources, routing, cache, streams |
| `swarm` | 13 | 4,446 | DAG runtime + 30 preset teams |
| `portfolio` | 13 | 3,645 | Read-only multi-broker aggregation |
| `shadow_account` | 11 | 2,915 | Journal -> rules -> replay -> PDF |
| `strategy_discovery` | 9 | 2,678 | Evidence-gated facade |
| `memory` | 8 | 2,592 | Persistence + lifecycle + compression |
| `scheduled_research` | 9 | 2,455 | Playbooks + proposals + verdict |
| `session` | 9 | 2,252 | SSE bus + FTS5 search |
| `entities` | 4 | 2,199 | Non-bar asset spine (irregular cash flows) |
| `strategy_store` | 8 | 1,719 | SDM artifacts + decay state machine |
| `scheduling` | 6 | 1,395 | Scheduler kernel + trigger grammar |
| `goal` | 5 | 1,311 | Research goals |
| `research_artifacts` | 7 | 1,182 | Immutable versioned artifacts |
| `governance` | 3 | 1,141 | Hash-chained ledger + run manifest |
| `br_data` | 11 | 1,033 | Brazil official datasets |
| `openbb_bridge` | 6 | 864 | OpenBB Workspace custom agent |
| `research_lab` | 6 | 736 | Cost sensitivity + frozen walk-forward |
| `hypotheses` | 3 | 635 | Hypothesis registry |
| `core` | 3 | 693 | Subprocess backtest runner + run state |
| `channelsui` | 8 | 366 | WebUI channel adapters |
| `pixel_agents` | 3 | 315 | Manual research task board |
| `security` | 5 | 248 | Injection scanner + workspace access |

---

## 2. Mechanics worth naming (module by module)

### 2.1 Agent loop and context

`agent/src/agent/loop.py` is a hand-written ReAct loop (79 KB), not LangGraph.
`pyproject.toml` declares `langgraph`, `langgraph-checkpoint` and
`langgraph-sdk`, but **no module imports them** (verified across the tree).
LangChain is used only for the provider clients.

Five-layer context strategy (`loop.py` header, implemented in
`context_compact.py`):

1. `_microcompact` — prune old tool results under pressure
2. `_context_collapse` — fold long text, **zero LLM calls**
3. `_auto_compact` — LLM summary with tail-token protection
4. `compact` tool — the model can request compaction
5. `_ITERATIVE_UPDATE_PROMPT` — the Nth compaction updates the prior summary

`context_budget.py` supplies `ContextMeter`, `is_context_overflow` and
`parse_context_limit`, so overflow is detected from provider errors instead of
guessed.

`tool_loading.py` implements `DeferredToolRegistry`: all tools stay in the
catalog, only `initial_tools` + `load_tools` are exposed per question, and
`request_definitions()` returns the unmodified schemas for the exposed set.

`instrument_identity.py` (46 KB) resolves symbol shapes and owns an
`IdentityLedger` that gates tools on resolved identity; it deliberately has no
answer validator or text rewriting.

### 2.2 Tools

`BaseTool` carries execution semantics Eclipse's `ToolDefinition` does not:

```python
repeatable: bool = False
is_readonly: bool = True
deterministic: bool = False            # cache identical calls
replay_after_compaction: bool = False  # restore exact readonly result
```

`_result_paging.py` pages **whole records** with a self-describing envelope
(`paging` block: total / returned / resume point), because a 28,498-character
payload delivered roughly 12 of 40 quarters.

`redaction.py` is sink-aware: `redact_internal_paths`, `redact_payload`,
`is_sensitive_arg`, with an `ARGUMENTS_SINK` concept; it scrubs credential and
PII keys before any event stream, trace or live audit sees them.

`_shell_safety.py` blocks killing Python processes by name (the agent must not
kill its own host).

### 2.3 Backtest and venue rules

`backtest/engines/` has 15 engines; `base.py` is 111 KB and defines the
execution contract:

```
can_execute(symbol, direction, bar)   round_size(raw, price)
limit_band(...)                       calc_commission(size, price, direction, is_open)
apply_slippage(price, direction)      capital_credit()
available_cash(ts)                    projected_reduction_buying_power(...)
can_liquidate_at_end(symbol, ts)      _plan_rejection_metrics()
```

`china_a.py` states and enforces: T+1, no retail shorting, +/-10%/20%/30%
price limits by board, 100-share lots (200 STAR / 100 Beijing then 1-share
steps), CNY 5 minimum commission at 0.025% bilateral, 0.05% sell-side stamp
tax, 0.001% transfer fee. Other engines add their own rules (Argentina 42
rule hits, crypto 50, Vietnam 33, Korea 20, India 23, options 36).

`loaders/registry.py` holds `VALID_SOURCES` and `FALLBACK_CHAINS` per market,
e.g. `a_share: [tencent, eastmoney, baostock, yahoo, akshare, tushare, local]`,
with the reason a source was retired recorded inline (mootdx, 2026-10-08).

`core/runner.py` executes generated `signal_engine.py` in a subprocess with an
AST scrubber (`_FORBIDDEN_IMPORT_MODULES`, `_FORBIDDEN_IMPORT_PREFIXES`,
`_reject_forbidden_getattr`), optional uid/gid drop, `RLIMIT_AS` (4 GB),
`RLIMIT_NOFILE` and an ephemeral HOME re-exposing only `cache` and
`data-bridge`.

### 2.4 Data gateway

38 registry sources; `NetworkRouter` keys health by `(scope, source)` where
scope is capability x market, backs off `cooldown * 2**(failures-1)` capped at
`lifetime`, spends at most one half-open probe per scope per cooldown, and
treats a success in another scope as *evidence for a probe*, never as data for
this scope.

`cache.py` keeps only bounded serialized bytes (never parsed chains);
`calendars.py` validates exchange sessions; `history_store.py` keeps
quota-controlled resumable datasets outside the checkout; `streams.py` is a
demand-driven quote distributor.

The repository-root `tools/` directory is a 25-script gateway soak suite:
`gateway_soak.py` (41 KB), `gateway_ten_job_restart_probe.py`,
`gateway_memory_pressure.py`, `gateway_quota_probe.py`,
`gateway_scan_contention_probe.py`, `gateway_stream_latency.py`, plus three
CI gates with their own tests.

### 2.5 Quant math

`quantlib/` ships 22 named modules: Brinson-Fachler with Carino linking,
copula, credit (Altman Z, Merton/KMV, CDS), purged+embargoed CV, event study,
fixed income (day counts, curve fitting), fund math on irregular cash flows,
market impact, microstructure (VPIN, Roll, Amihud), multiple testing,
neutralization + factor PCA, options, performance with client cash flows,
HRP/ERC, VaR/CVaR/EVT, Heston, VaR backtesting (Kupiec/Christoffersen), and
explicit rate units.

### 2.6 Alpha research

`factors/registry.py` AST-scans `zoo/**` modules, validates metadata, and
lazy-imports on compute. `bench_runner.py` computes IC mean/std/IR/positive
ratio per alpha; `bench_runner_strict.py` adds a **random control** and a
train/test OOS split. `data_availability.py` declares field-level availability
so an alpha with missing fundamental inputs is reported unavailable rather than
silently degraded.

`strategy_store/decay.py` is a pure state machine with explicit thresholds
(IC ratio 0.7/0.5/0.3, IR 1.0/0.5/0.1, IC positive ratio 0.55/0.45/0.35,
Sharpe 1.0/0.5/0.0) and consecutive-signal counts for transition
(`warnings_for_monitoring=3`, `warnings_for_decayed=2`,
`critical_for_disabled=3`).

### 2.7 Research lifecycle

`research_artifacts/` stores immutable revisions; `comparison.py` and
`comparison_export.py` produce deterministic JSON/Markdown diffs (content,
evidence additions/removals, pure reorderings, provenance changes);
`financial_facts.py` is an opt-in facts envelope.

`research_lab/studies.py` implements two experiments on one frozen input
snapshot: `cost_sensitivity` (re-execute the same strategy under declared cost
scenarios) and `walk_forward` (select on train, freeze, then OOS/holdout).

`hypotheses/registry.py` is a durable registry whose records link to run cards;
`goal/` holds research goals with policy and store.

### 2.8 Shadow account

`extractor.py` mines profitable roundtrips into a `ShadowProfile` of 3-5
if-then rules; `codegen.py` renders a signal engine; `backtester.py` replays
across markets per settlement currency; `reporter.py` produces an 8-section
HTML/PDF report with delta-PnL attribution against realized trades.

### 2.9 Trading and live

19 connectors under `trading/connectors/` (alpaca, binance, dhan, etoro, futu,
ibkr, kis, longbridge, mstock, mt5, okx, robinhood, scalable, shoonya, tiger,
toss, trading212, upbit, zerodha). `capability_matrix.py` renders declared
capabilities into README + guide between markers, with a CI drift guard, and
labels them *declarations, not runtime verification*.

`live/enforcement.py` checks in fixed order (exclude-list, instrument, asset
class, single-order notional, total exposure, leverage, daily count, funding),
fails closed on any unparseable input, and returns `BreachEvent` kinds
`universe | instrument | quantitative` (structural -> deny; quantitative ->
pause). Supporting modules: `halt.py` kill switch, `daily_count.py` atomic UTC
counter, `pending_action.py` crash-safe side-effect marker, `order_guard.py`
gate, `sdk_order_gate.py` for direct-SDK connectors, `tap_forward.py`
(Tool Authorization Protocol proxy).

### 2.10 Portfolio, entities, Brazil

`portfolio/` aggregates read-only broker snapshots, converts FX, validates
ISO-4217, imports extraETF exports, and produces **proposals only** — the
module docstring states it has no execution transport.

`entities/cashflow.py` is the non-bar asset spine: holder-perspective sign
convention enforced at construction (`capital_call` with positive amount is
rejected), `is_valuation` excluded from `total()`, so fund IRR/TVPI can be
computed from irregular flows.

`br_data/` syncs B3 COTAHIST (fixed-width 245-char Latin-1 records, documented
1-based column layout), CVM company/fund registries, Banco Central SGS series
and Tesouro Direto into one SQLite file; the daily cadence is a protected
system job (`system:br-data-sync`), not a sleep loop.

### 2.11 Swarm, memory, skills

`swarm/runtime.py` schedules workers by topological layer, parallel within a
layer; `task_store.py` owns DAG validation; `evidence_handoff.py` carries
observations between committee roles *without granting sibling access*;
`grounding.py` pre-fetches market data for symbols in `user_vars`. 30 preset
YAML teams ship as content.

`memory/` adds lifecycle hygiene Eclipse does not have: quality scoring with
access tracking, Ebbinghaus-inspired decay, capacity GC, Raw->Daily->Digest
compression, FTS5 index, BM25 semantic links. All gated by feature flags
(`VT_MEMORY_QUALITY`, `VT_MEMORY_GC`, `VT_MEMORY_DECAY`).

89 `SKILL.md` files, including chanlun, elliott-wave, ichimoku, harmonic, SMC,
convertible-bond, credit-analysis, geopolitical-risk, perp-funding-basis,
liquidation-heatmap, stablecoin-flow, token-unlock-treasury, hk-connect-flow,
earnings-revision, thesis-tracker, vnpy-export.

### 2.12 API, session, CLI

`api/security.py` rejects credentialed wildcard CORS, allows additive origins
via an opt-in env var, enforces a loopback Host allow-list as DNS-rebinding
defence before auth bypasses, issues short-lived SSE tickets for EventSource,
and gates shell tools.

`session/events.py` is an SSE bus with `last_event_id` recovery and buffering,
written to be thread-safe across a background producer and an asyncio consumer.
`session/search.py` is an FTS5 index over past sessions.

`cli/main.py` is the REPL (66 KB) with slash commands, proposal rendering for
mandates and scheduled jobs, halt controls; `_legacy.py` (271 KB) is the
pre-split monolith kept for the older entry points.

### 2.13 Governance

`governance/ledger.py` is a hash-chained, fsynced, append-only JSONL ledger:
each record embeds `seq` and `prev_record_hash`, then hashes both plus its
payload, so editing any earlier record breaks every later hash; POSIX
`flock`/`msvcrt` locking guards the read-tail+append section.

`governance/manifest.py` is a *methodology* fingerprint: system prompt hashed,
skills as `(name, content_hash)`, tool names plus a hash, curated package
versions; `timestamp` and `run_id` are recorded but deliberately excluded from
`manifest_hash` so identical methodology hashes identically across days.

---

## 3. Gap register — exact Eclipse contract each item changes

Each row names the Eclipse file, the current contract, and the proposed
contract. Nothing here is implemented yet.

### G1 — Deferred tool exposure

**Vibe:** `tool_loading.DeferredToolRegistry` + `load_tools`.
**Eclipse today:** `ToolRegistry.schemas(allowed)` in `python/harness/tools.py`
returns every allowed schema each turn; `graph.py` binds them via
`model.bind_tools(lc_tools)`. `surface.py` only *ratchets* size
(`MAX_SURFACE_ADDED_SCHEMA_CHARS = 120_000`).
**Proposed:**

```python
# tools.py
def schemas(self, allowed: Optional[set[str]] = None, *,
            exposed: Optional[set[str]] = None) -> list[dict[str, Any]]: ...

# new: python/harness/tool_exposure.py
@dataclass(frozen=True)
class ExposureState:
    initial: frozenset[str]
    exposed: frozenset[str]
    def can_expose(self, name: str, allowed: set[str] | None) -> bool: ...

# new tool, registered read/deterministic/risk="none"
async def load_tools(args: {"names": list[str]}, ctx: ToolContext) -> str
```

Invariant: `load_tools` may only expose `name in effective_allowlist`. A test
must assert it cannot widen.
**Why:** ~400 tools today; the ratchet proves the pressure without relieving it.

### G2 — Zero-cost collapse + iterative summary

**Vibe:** `context_compact._context_collapse`, `_ITERATIVE_UPDATE_PROMPT`.
**Eclipse today:** `compaction.py` has `HistoryCompaction`, `build_skeleton`,
`build_compaction_prompt(requests, answers)`, `render_compaction_block`; every
compaction is a fresh model call and there is no sub-LLM stage.
**Proposed:**

```python
# compaction.py
def collapse_tool_results(turns, *, head: int, tail: int,
                          min_chars: int) -> tuple[list[Any], CollapseReport]: ...
def build_compaction_prompt(requests, answers, *,
                            prior: CompactionResult | None = None) -> str: ...
```

Collapse must be reversible-by-reference: the full payload stays in the run
store, and the collapsed block carries a digest plus a marker. Honesty rules in
the module docstring stay unchanged.

### G3 — Router probe budget

**Vibe:** `data_gateway/routing.NetworkRouter` (scope-keyed health, half-open
probes, cross-scope evidence).
**Eclipse today:** `market/router.py::ProviderRouter.provider_order(capability,
instrument)` with a single `CircuitBreaker` per provider from `mcp/circuit.py`.
**Proposed:**

```python
class ProviderRouter:
    def provider_order(self, capability: str,
                       instrument: Optional[CanonicalInstrument], *,
                       scope: Optional[str] = None) -> tuple[str, ...]: ...
class ProbeBudget:
    def claim(self, scope: str, provider: str) -> bool: ...
```

Invariant to encode in a comment: *a success elsewhere is evidence for a
probe, never data for this scope.*

### G4 — Generated capability matrix + CI drift gate

**Vibe:** `trading/capability_matrix.py` (marker blocks + drift guard).
**Eclipse today:** declarations live only in code —
`trade/model.py::BrokerKind.to_dict()`, `trade/registry.py::list_kinds()`,
`market/providers.py::ProviderDescriptor.to_dict()`, `default_providers()`.
At the time of the analysis: 4 broker kinds and 13 providers, undocumented as a
table. (Now 5 kinds, generated into `docs/trading.md` with a drift gate.)
**Proposed:** `scripts/gen-capability-matrix.mjs` renders marker-delimited
tables into `docs/trading.md` and `docs/data-sources.md`;
`npm run check:capabilities` fails on drift and is wired into
`scripts/check-all.js`. Every cell says *declared, not verified*.

### G5 — Endpoint DNS pinning

**Vibe:** `providers/endpoint_guard.py` resolves once, refuses non-public
addresses, connects to the checked IP (no rebind window), and special-cases
Fake-IP proxy ranges.
**Eclipse today:** custom `base_url` reaches the LangChain client directly;
no rebind-safe resolution found in `model_runtime/` or `models.py`.
**Proposed:** `python/harness/model_runtime/endpoint_guard.py` with
`resolve_public_endpoint(url) -> ResolvedEndpoint`, used only when a
user-supplied endpoint is configured.

### G6 — Venue rule matrix (largest correctness gap)

**Vibe:** `backtest/engines/*` (`can_execute`, `round_size`, `limit_band`,
commission/tax/settlement per market).
**Eclipse today:** `quant/strategy.py::StrategySpec` has `execution:
ExecutionAssumptions`; `quant/engine.py::BacktestConfig(initial_capital, start,
end, risk_free_rate, random_seed, execution_override, max_bars,
corporate_actions, code_version)`. `quant/venues.py` is about strategy
*languages*, not markets. No T+1, price limits, lot rounding or stamp duty.
**Proposed:**

```python
# new: python/harness/quant/venue_rules.py
@dataclass(frozen=True)
class VenueRules:
    can_execute(symbol, direction, bar) -> bool
    round_size(raw: float, price: float) -> float
    limit_band(symbol, bar) -> tuple[float, float] | None
    commission(size, price, direction, is_open) -> float
    taxes(size, price, direction) -> float
    settlement_days: int
def rules_for(venue: str) -> VenueRules: ...   # us_equity, a_share, hk, ...

# strategy.py
class StrategySpec(...):
    venue: str = "us_equity"
```

**Why first among correctness items:** a non-US backtest without these rules is
structurally wrong, and a wrong number is worse than an absent one.

### G7 — Alpha zoo (library size, not machinery)

**Vibe:** 460 alphas across alpha101 / gtja191 / qlib158 / academic /
fundamental.
**Eclipse today:** `factors/library.py::BUILTIN_FACTORS` — 18 records with
`name, family, direction, lookback, description, expression, inputs,
available`; safe `stats.formula` engine; strong tooling
(`analyze_factor_redundancy`, `analyze_factor_stability`,
`compose_alpha_model`, `promote_factor_to_strategy`).
**Proposed:** extend the record with `reason`, `source`, `license`; add
`factors/zoo/{alpha101,gtja191,qlib158,academic,fundamental}.py`; port Vibe
expressions into the Eclipse DSL (never Python), preserving `available=False`
honesty and per-library NOTICE provenance. Timebox; ship the verified subset.

### G8 — Strict bench protocol

**Vibe:** `bench_runner_strict.py` — IC + random control + train/test OOS.
**Eclipse today:** `quant_bench/runner.py` grades routing, honesty,
invariants, workflow, reproducibility on cases; factor evaluation reports
IC/IR without a random control or an OOS split.
**Proposed:** `StrictBenchConfig(control="random", split=(0.7, 0.3))` and a
report carrying `ic_mean, ic_ir, ic_pos_ratio, control_ic_mean, oos_ic_mean`.

### G9 — Team preset library

**Vibe:** 30 YAML teams with full buy-side prompts.
**Eclipse today:** `team/model.py::TeamDefinition(id, name, objective,
agent_id, members, subtasks, policy, metadata)`; teams are authored, not
bundled; 4 built-in agents.
**Proposed:** `team/presets/*.yaml` + `team/presets.py` loader producing
`TeamDefinition`; add `TeamSubtask.evidence_required: bool` mapped onto
`team/service.py::_evidence_exists`. Translation rules: `{upstream_context}` ->
`_render_context` + explicit `dependsOn`; "run in bash" -> `quant.*` /
`finance.*` nodes.

### G10 — Whole-record result paging

**Vibe:** `_result_paging.py` (whole records + `paging` envelope).
**Eclipse today:** `tools.py::bound_tool_text(text, limit) -> (text, truncated,
shown, total)` appends an unmistakable non-JSON marker. Honest, but a partial
list is not resumable.
**Proposed:** `page_records(records, limit, *, cursor) -> (text, paging)` where
`paging = {total, returned, next_offset}`; keep the existing marker as the
fallback for non-list payloads.

### G11 — Memory lifecycle

**Vibe:** `memory/lifecycle.py` — quality scoring, decay, capacity GC.
**Eclipse today:** `eclipse_memory/` has 24 modules and `consolidate_active()`
merging, but no decay, GC or quality score (grep: `decay`=1, `garbage|gc_`=0,
`quality_score`=0).
**Proposed:** `eclipse_memory/lifecycle.py` with `score_access(id)`,
`decay_importance(now)`, `gc_to_capacity(max_entries)`, all opt-in and
auditable through the existing memory event log.

### G12 — Artifact revision comparison

**Vibe:** `research_artifacts/comparison.py` + `comparison_export.py`.
**Eclipse today:** `artifacts/service.py` registers immutable artifacts
(`register`, `get`, `list`); no deterministic revision diff.
**Proposed:** `artifacts/compare.py::compare_revisions(a, b) ->
RevisionDiff(added, removed, reordered, provenance_changes)` plus JSON/Markdown
export.

### G13 — Scheduled prompts name capabilities, not tools

**Vibe:** `scheduled_research/playbooks.py` — *"No template names a tool. A
playbook states the data capability it needs in plain language ... so the
templates survive changes to the tool surface."* Prompt persisted once and
re-sent unchanged, so nothing may be baked in that is only true on the authoring
day.
**Eclipse today:** `automation/scheduling_tools.py` + `job_describe_template`;
prompt text is free-form.
**Proposed:** adopt the rule as a documented template constraint (and a lint on
bundled templates), not a code change.

### G14 — Evaluate later (no contract proposed)

`br_data/` (Brazil B3/CVM/BCB/Tesouro), `entities/` (non-bar asset spine),
`openbb_bridge/` (OpenBB Workspace custom agent), `pixel_agents/` (manual task
board — Eclipse already has `board_read/board_write/board_search` in
`spawn/tools.py`), `channelsui/` (only meaningful with the WebSocket channel).
These are genuine absences but require a product decision, not a port.

---

## 4. Priority

| Tier | Items | Rationale |
|---|---|---|
| 1 | G4, G1, G3, G5, G13 | Self-contained, verifiable, small; G4 has no runtime risk |
| 2 | G6, G8, G10, G11, G12, G2 | Correctness and research quality |
| 3 | G7, G9 | Content imports gated on review capacity |
| Later | G14, broker breadth (5 -> more connectors), IM channel breadth (19 -> 19) | Product decisions |

---

## 5. Where Eclipse is ahead (kept explicit)

- Tool catalog: ~400 tools (255 `_def` + ~143 direct `ToolDefinition`) vs 126.
- Authorization: 28 modules including `security/floor.py`,
  `capabilities.py`, `effect_tokens.py`, `appcontainer.py`, `tenant_store.py`.
- Money guardrails and fiduciary advisory: no Vibe analogue.
- Evaluation science: 45 modules vs Vibe's 43-file eval harness (comparable
  machinery, far more Eclipse cases and gates).
- Observability: 24 modules (OTLP, Langfuse, Sentry, SLO, anomaly, sampling).
- Graph/visual authoring: 64 `graph_runtime` files + React Flow editor +
  registry parity manifest.
- Memory content depth: 24 modules vs 8.
- Desktop product: 33 screen directories, 471 API routes, signed updates.

## 6. How Vibe renders output, and how Eclipse compares

Vibe splits presentation in two:

- **Web** — ECharts in React: `frontend/src/components/charts/` has 17 chart
  components (equity, mini-equity, drawdowns, monthly-returns heatmap, annual
  returns, Monte-Carlo paths, walk-forward, correlation matrix, distribution,
  attribution waterfall + cumulative, rolling beta/alpha, regime timeline,
  options payoff + scenario matrix, candlestick) and 89 `echarts` references
  across the frontend. Charts are built client-side from run artifacts.
- **PDF/HTML** — `matplotlib` appears in exactly three modules:
  `shadow_account/reporter.py`, `shadow_account/fonts.py`, `tools/pdf_report.py`,
  producing multi-section reports with embedded images.

Eclipse has the deeper *computation* side — `quant/visuals.py` exposes 14 figure
types through one catalog (`equity`, `underwater`, `monthly_returns`, `exposure`,
`trade_distribution`, `trade_scatter`, `rolling_risk`, `cost_waterfall`,
`montecarlo`, `regime_attribution`, `parameter_surface` (3-D), `walkforward`),
each carrying `available` + `reason` instead of silently vanishing — and one
chart engine (`charts/`) that draws a spec to PNG or Plotly.

The measured gap was in **output**, not in figures: `quant/report_export.py`
produced a self-contained HTML report with metrics, assumptions, warnings and
the reproducibility digest, but **no charts**. Vibe's run page and PDF both
show them.

**Fixed in Phase 1:** the HTML export now embeds the artifact's `core` + `risk`
figures as inline `data:image/png;base64` images, built by the same
`quant.visuals` builders and rendered by the same chart engine. No JavaScript,
no external asset, and rendering is best-effort — a failure prints
`Figures unavailable: <reason>` and the numbers still render.

Remaining output gaps (not yet done): monthly-returns heatmap and correlation
matrix are not in Eclipse's figure catalog; the browser run page has no
`walkforward` or `parameter_surface` view; and there is no PDF route (HTML only).

## 7. Implementation status

| Gap | Status | Where |
|---|---|---|
| G4 capability matrix + drift gate | **Done** | `harness/trade/capability_matrix.py`, `scripts/docs-brokers.js`, `docs/trading.md`, `npm run docs:brokers:check` |
| G1 tool exposure | **Already existed** — `tool_disclosure.py` (BM25-ranked, tiered catalogue + `tool_search`/`tool_invoke`); the missing third step (see a hidden tool's schema) added as `load_tool_schema` | `harness/tool_schema_load.py`, `harness/tool_disclosure.py`, `harness/service.py`, `harness/agents.py` |
| G2 context collapse + iterative summary | **Done (opt-in)** — `collapse_text/turn/turns` wired into `_bounded_history` behind `BE_HISTORY_COLLAPSE`; `build_compaction_prompt(prior=…)` + `iterated` flag | `harness/compaction.py`, `harness/history.py` |
| G3 router probe budget | **Done** — `attempt_order` + `ProbeBudget` (scope-keyed, one probe per cooldown, cross-scope evidence) | `harness/market/router.py` |
| G5 endpoint DNS pinning | **Done (validation)** — IP-literal private/loopback refusal always; hostname resolution opt-in via `BE_ENDPOINT_PINNING`; connect-time pinning not implemented (stated) | `harness/model_runtime/endpoint_guard.py`, `harness/models.py` |
| G6 market execution rules | **Done** — market rules + `StrategySpec.market` + validation + engine enforcement (lots, limit bands, T+1) | `harness/quant/market_rules.py`, `harness/quant/strategy.py`, `harness/quant/engine.py` |
| G7 alpha zoo | **Partial** — **479 zoo entries** (16 academic + 101 Alpha101 + 158 Qlib + 189 GTJA191 + 15 fundamental declared-but-blocked) `factors/panel.py` provides cross-sectional rank/scale; the rest need `vwap`/`adv`, a regression (`BETA`/`RSQR`/`RESI`), or a primary-source reconciliation of GTJA's operator definitions (stated, not approximated) | `harness/factors/zoo/`, `harness/factors/panel.py`, `harness/stats/formula.py` |
| G8 strict bench | **Done** — random control + train/test OOS, `oosDecay`, `beatsControl` | `harness/factors/strict_bench.py` |
| G9 team preset library | **Done** — 30 bundled finance teams (`investment_committee`, `quant_strategy_desk`, `portfolio_risk_review`, `earnings_review_desk`, `macro_rates_fx_desk`, `equity_research_team`, `risk_committee`, `technical_analysis_panel`) with `evidence_required` + a validating YAML loader; the bundle matches the 30-desk reference count | `harness/team/preset_library.py`, `harness/team/presets/` |
| Broker breadth | **Done** — 19 read-only kinds (`alpaca`, `ibkr`, `mt4_bridge`, `mt5`, `trading212`, `zerodha`, `tradier`, `okx`, `binance`, `kraken`, `coinbase`, `bybit`, `deribit`, `oanda`, `bitget`, `gateio`, `bitstamp`, `coincheck`, `bitfinex`); a connector is now a two-file change (adapter + `register_kind`) and the matrix is generated | `harness/trade/adapters/trading212.py`, `harness/trade/registry.py` |
| IM channel breadth | **Done** - 19 providers incl. outbound-only dingtalk and mattermost; the library now matches the reference's 19 platform families | harness/channels/registry.py, harness/channels/providers/ |
| G12 artifact revision diff | **Done** — `artifacts/compare.py` (checksum/size, provenance, note, metadata add/remove/change) + Markdown export; no byte-level line diff (stated) | `harness/artifacts/compare.py` |
| G10 result paging | **Already existed** — `tool_outputs.py` pages truncated output with `offset`/`nextOffset` | — |
| G11 memory lifecycle | **Already existed** — retention/expiry sweep + preview + maintenance lease/status (`eclipse_memory/service.py`, `store.py`) | — |
| Output charts in exported reports | **Done** | `harness/quant/report_export.py` |
| G13 scheduled-prompt capability rule | **Done** - jobs/prompt_policy.py + a lint test over every bundled job template; two templates were fixed because the lint caught real tool ids in their prompts | harness/jobs/prompt_policy.py |
| G14 non-bar entities | **Done** - `harness/entities/` (dated cash flows, holder-perspective sign enforced at construction, valuations excluded from totals, XIRR, TVPI) | `harness/entities/cashflow.py`, `docs/harness/non-bar-assets.md` |
| G14 B3 COTAHIST parser | **Done** - fixed-width 245-char records, documented 1-based column map, 2 implied decimals, FATCOT lot factor, named errors | `harness/br_data/cotahist.py`, `docs/harness/brazil-market-data.md` |
| G14 B3 sync + SQLite store | **Done (offline)** - `BrStore` (keyed trade_date+ticker, idempotent upsert, `sync_runs`), `sync_archive` over a local zip, `status()` | `harness/br_data/store.py`, `harness/br_data/sync.py` |
| G14 B3 download | **Done (injectable transport)** - `download_archive` (atomic .part→rename, zip proof, size cap, named HTTP/transport errors), `sync_from_url` | `harness/br_data/download.py` |
| G14 OpenBB bridge | **Done (protocol, offline)** - tolerant QueryRequest models, no-invented-identity history replay, fenced context injection, key-name-only handling, event→SSE mapping with secret whitelisting | `harness/openbb_bridge/`, `docs/harness/openbb-bridge.md` |
| G14 other BR datasets (CVM/BCB/Tesouro) + OpenBB HTTP route | **Done** - `csvtext` (decimal comma, both date orders, Latin-1/UTF-8), `cvm` (fund quota/net assets/flows, derived `netFlow` labelled), `bcb` (SGS series; unknown codes stay unnamed, gaps counted), `tesouro` (yields kept as published %, `Mania` typo tolerated), one `datasets` registry; OpenBB `GET /openbb/agents.json` + streaming `POST /openbb/v1/query` with no invented `modelSettings` | `harness/br_data/`, `harness/routers/openbb.py`, `harness/openbb_bridge/stream.py`; `dataset_store` tables (`cvm_funds`, `bcb_series`, `tesouro_bonds`) with idempotent upserts + `sync_dataset`; **scheduled registration** (`br_data/schedule.py`: due logic, per-dataset fetch, opt-in hourly loop) |

## 8. Non-goals

- **Generated-code backtests.** Eclipse stays declarative (`StrategySpec`);
  Vibe needs an AST scrubber plus subprocess isolation because its artifact is
  executable Python.
- **`langgraph` dependency theatre.** Declared in Vibe's `pyproject.toml`,
  imported nowhere; Eclipse actually uses it.
- **File-based memory hierarchy.** Eclipse's SQLite store and providers are
  stronger; only the lifecycle hygiene (G11) is worth taking.
- **`cli/_legacy.py`** (271 KB monolith) — nothing to learn there.
