---
title: Quant Engine — Trading, Backtesting & Research
status: Current
last-verified: 2026-10-11
---

# Quant Engine — Trading, Backtesting & Research

**Who this is for:** anyone working on backtesting, strategy evaluation, or any
part of `python/harness/quant/`.

**The one rule:** the LLM orchestrates (authors/edits strategy specifications,
calls tools, explains results); the **deterministic Python Quant Engine computes
everything** — fills, P&L, position sizes, drawdown, Sharpe, VaR. No layer
outside `harness/quant/` may compute a trading statistic, and the engine never
fabricates a value: unavailable inputs produce a typed error or an explicit
warning, never a silent zero.

## What it is

A modular, event-driven backtesting engine. The pipeline is explicit:

```
market data → indicator context → signal (rules) → risk → order
            → execution simulator → fill → portfolio → equity/exposure → metrics
```

## Ownership map

| Concern | File |
|---|---|
| Strategy contract, rule DSL, validation, semver | `quant/strategy.py` |
| Strategy IR schema identity, compatibility, migration, content hash | `quant/schema.py` |
| Portable strategy bundles (export/import + safety) | `quant/bundle.py` |
| Typed strategy graph model (visual builder authoring front) | `quant/graph_model.py` |
| Versioned strategy node registry + built-in nodes | `quant/nodes.py` |
| Strategy graph compiler (graph → canonical IR) | `quant/compiler.py` |
| Python Strategy SDK (in-process driver) | `quant/sdk.py` |
| Isolated Python strategy worker + managed runtime | `quant/sdk_worker.py`, `quant/sdk_runtime.py` |
| Reference Python strategies | `quant/examples/` |
| AI copilot support (signals, research plan, report, rule/sizing helpers) | `quant/copilot.py` |
| AI copilot agent tools | `quant/copilot_tools.py` |
| Benchmark-relative metrics (alpha/beta/IR/tracking error) | `quant/benchmark.py` |
| Governance, source inspection, multi-file projects, paper shadow runs | `quant/ops_tools.py` |
| Approved dependency policy | `quant/sdk_deps.py` |
| Rule evaluation over arrays | `quant/rules.py` |
| Causal indicators (EMA/SMA/RSI/ATR/MACD/Bollinger/…) | `quant/indicators.py` |
| Market-data adapter, point-in-time dataset, quality checks, MTF alignment | `quant/data.py` |
| Gateway → dataset resolution | `quant/datasets.py` |
| Order lifecycle + state machine | `quant/orders.py` |
| Commission / slippage / spread / impact / latency | `quant/execution.py` |
| Position sizing methods | `quant/sizing.py` |
| Pre-trade risk limits | `quant/risk.py` |
| Backtest simulation portfolio (cash/positions/P&L/exposure) | `quant/portfolio.py` |
| Performance / risk / trade statistics + definitions | `quant/metrics.py` |
| Event-driven loop + `BacktestResult` | `quant/engine.py` |
| Vectorized research engine (representable subset only) | `quant/vector_engine.py` |
| Standalone commission/slippage/spread/impact diagnostics | `quant/costs.py` |
| Bootstrap CIs + chronological out-of-sample split | `quant/validation.py` |
| Deflated Sharpe + Probability of Backtest Overfitting (CSCV) | `quant/multiple_testing.py` |
| Options pricing/IV/Greeks + multi-leg strategy analytics | `quant/options.py` |
| Continuous futures contract splice + back-adjustment | `quant/futures.py` |
| Advanced tools (engine selection, cost sim, OOS, bootstrap, compare) | `quant/advanced_tools.py` |
| Parameter spaces (dotted paths, ranges, grid/sample) | `quant/params.py` |
| Optimization (grid/random/evolutionary/Bayesian, objectives, Pareto, stability) | `quant/optimize.py` |
| Walk-forward (train/test, IS/OOS/combined, divergence) | `quant/walkforward.py` |
| Monte-Carlo (reshuffle/bootstrap/parameter/execution perturbation) | `quant/montecarlo.py` |
| Sensitivity + robustness + overfitting safeguards | `quant/robustness.py` |
| Shared research-result envelope | `quant/research.py` |
| Strategy + experiment persistence, artifacts | `quant/store.py` |
| Golden synthetic datasets | `quant/fixtures.py` |
| Background run runner (status/progress/cancel) | `quant/runner.py` |
| Agent tools | `quant/tools.py` |
| HTTP routes | `routers/quant.py` |
| Boot wiring | `quant/bootstrap.py` |
| UI tab | `src/components/screens/backtest/` + `src/lib/backtest/` |

## Point-in-time correctness (the anti-lookahead contract)

1. Every bar carries `data_available_at` (its close). The engine processes the
   merged timeline and only exposes a bar once it has closed.
2. Indicators are **causal**: the value at `i` uses only `≤ i`; the warm-up
   region is `NaN`, and a rule referencing a `NaN` operand is `False`.
3. Bar-processing order is fixed and tested: (1) fill orders submitted on an
   earlier bar, (2) check protective legs against the stop levels carried *into*
   the bar — a trailing stop is advanced with this bar's favorable extreme only
   if it did **not** trigger, so a same-bar high cannot tighten a stop that the
   same bar's low already breached, (3) evaluate exit signals, (4) evaluate entry
   signals at the close, (5) snapshot. Nothing computed from bar `i` fills an
   order on bar `i`. Position sizing and protective-bracket sizing are likewise
   causal: volatility sizing uses only bars up to and including the decision bar,
   and an ATR-based stop/trail is measured from the **decision** bar
   (`order.submitted_index`), never the later fill bar.
4. Multi-timeframe: a higher-TF bar is available to a primary bar only when the
   higher bar's close is at or before the primary bar's close
   (`data.align_higher_to_primary`). Confirmation indicators are namespaced
   `key@tf`; higher-TF price fields are exposed as `close@tf`, etc.

## Execution model

- Commission: `none | fixed | percentage | per_share | per_contract | tiered`
  (tiered is marginal on notional).
- Slippage: `none | fixed | percentage | volatility | volume | randomized`
  (randomized is seeded for reproducibility).
- Spread: `none | fixed | percentage | bps | historical`. `historical` uses the
  bar's own absolute spread when the dataset carries a `spread` column; if it
  does not, the cost is zero **with a recorded `HISTORICAL_SPREAD_UNAVAILABLE`
  warning**, never silently.
- Market impact: `none | linear | sqrt` (linear and square-root participation laws;
  both are *assumed* relationships, not calibrated estimates).
- Latency: `latency_bars`.
- A filled `Fill.price` already embeds slippage/spread/impact adversely; those
  components are reported for audit but only `commission` is charged separately
  to cash. A frictionless run only ever results from an explicit `none`
  configuration (`ExecutionAssumptions.is_frictionless`).
- A completed trade's `net_pnl` is gross P&L **minus both the entry and the exit
  commission** (the entry share is allocated proportionally on partial closes),
  so `sum(trade.net_pnl)` reconciles with the cash ledger. `Position.realized_pnl`
  is maintained per symbol.

## Reproducibility & experiments

Each experiment stores the full envelope: strategy id+version, symbols,
interval, range, initial capital, random seed, engine version, execution
assumptions and metrics. Metadata lives in the ONE `agent-memory.db` connection
(additive, idempotent DDL); the large result series (equity/drawdown/trades/
orders/fills) are written as gzipped JSON artifacts under
`.black-eclipse/quant/experiments/`. Same inputs + same seed ⇒ identical result.

## Strategy IR identity, immutable versions & portability

The strategy contract (`StrategySpec`) is the canonical **Strategy Intermediate
Representation**; the visual builder, the Python lab and the AI copilot all
converge on it, and it is the source of truth — never the graph.

- **Schema identity** (`schema.py`): `STRATEGY_SCHEMA_VERSION` names the wire
  format. `schema_compatible` accepts any same-major version (additive changes
  stay loadable) and refuses a different major. `migrate` applies an ordered,
  lossless migration registry (empty at 1.0.0) and **preserves unknown keys**
  rather than dropping them. `spec_content_hash` is a sha256 over the
  canonicalized IR dict (order-independent).
- **Immutable versions** (`store.py`): `QuantStrategyVersion` carries
  `contentHash` + `schemaVersion`. Once an experiment references a version, the
  version is **frozen** — re-saving *different* content under it raises
  `STRATEGY_VERSION_IMMUTABLE` (`409`) and the caller must bump the version;
  identical content re-saves are a no-op. Editing is always a new version.
  Unreferenced versions may still be corrected (backward compatible).
  `version_meta` reports hash/schema/reference-count; `diff_versions` returns a
  structural added/removed/changed diff (`GET /quant/strategies/{id}/diff?a=&b=`).
- **Portable bundles** (`bundle.py`): `export_strategy` / `import_strategy`
  produce/consume a self-describing zip (`manifest.json` + `strategy.json` +
  `README.md`) and a JSON form (`GET /quant/strategies/{id}/export?format=json`).
  Import is **untrusted input**: size caps (compressed + uncompressed), member
  cap, path-traversal rejection, no on-disk extraction, schema gating, a
  hash-mismatch warning, and re-validation through the normal schema path with
  unknown keys preserved. The Backtest UI surfaces export/import/diff in the
  `StrategyPortability` panel; three agent tools (`export_strategy`,
  `import_strategy`, `diff_strategy_versions`) expose the same store/engine.

## Visual Strategy Builder — the graph compiler

The Visual Strategy Builder is a **typed strategy graph** that compiles to the
SAME canonical IR as every other authoring mode. It is deliberately NOT a
general-purpose workflow graph.

- **Graph** (`graph_model.py`): identity + nodes (`id`, `type`, semver, config) +
  typed edges. Shape-checked before compilation.
- **Node registry** (`nodes.py`): each node has a stable `type_id`, its own
  semver (same-major compatible), typed ports (`series`/`number`/`rule`/`any`),
  a config schema/defaults and a pure `compile(ctx, node, inputs)`. Built-ins
  span data/universe, every catalog indicator (+ Bollinger/MACD output selectors),
  logic (compare / cross-above-below / group / constant), trading (entry/exit),
  sizing, stops/targets and risk limits. Add a node without touching the compiler.
- **Compiler** (`compiler.py`): parse → resolve types/versions → validate
  ports/types → deterministic topological order (cycle detection) → compile →
  assemble `StrategySpec` → shared `validate_strategy`. Returns structured
  diagnostics (`UNKNOWN_NODE_TYPE`, `UNSUPPORTED_NODE_VERSION`, `TYPE_MISMATCH`,
  `MISSING_INPUT`, `CYCLE_DETECTED`, `DUPLICATE_NODE_ID`, `BAD_CONFIG`, plus the
  IR validation codes) and a **source map** (spec path → node id). Compilation is
  **deterministic** for equivalent graphs.
- **Surfaces**: `compile_strategy_graph` / `validate_strategy_graph` /
  `list_strategy_nodes` agent tools and `POST /quant/graph/compile`,
  `POST /quant/graph/validate`, `GET /quant/graph/nodes`.
- **No separate UI**: the graph is authored through the CHATBOT (the agent
  composes a `StrategyGraph` — often compiled from a natural-language request —
  and calls `compile_strategy_graph`/`validate_strategy_graph`). The graph is a
  strategy representation only; arbitrary Python is never forced into a graph —
  unsupported constructs remain Python-first.

## Python Strategy Lab — the SDK and managed runtime

A strategy can be authored as ordinary Python (`quant/sdk.py`) and run on the
SAME engine as every other mode.

- **SDK**: subclass `Strategy` with `initialize(ctx)`, `on_data(ctx, bar)`,
  `on_fill`, `on_order_update`, `on_stop`. `Context` exposes params, declared
  indicators (`ctx.indicator(id)`), causal `ctx.history(field, n)`, position and
  portfolio state (`ctx.position/cash/equity`), a seeded `ctx.rng`, and order
  intents (`ctx.buy/sell/close/order`). Stops/targets/sizing/risk are set in
  `initialize`.
- **Shared accounting**: the driver subclasses `BacktestEngine`, so fills
  (next-bar, with commission/slippage/spread/impact/latency), protective legs,
  the risk engine, portfolio accounting and metrics are the SAME code path as a
  declarative backtest. The SDK only supplies per-bar decisions.
- **Managed runtime**: `run_strategy_source` writes the source + data to a temp
  dir and launches `sdk_worker.py` in a **separate process** with `python -I`, a
  **scrubbed environment** (no PYTHONPATH, no credentials/provider keys), a
  **wall-clock timeout** (killed on overrun), an **output-size cap**, and POSIX
  CPU/address-space limits where supported. Results are rehydrated into a typed
  `BacktestResult`. This is process isolation, not a container: a hard
  filesystem/network boundary is the harness OS sandbox's responsibility, so the
  capability is advertised `partial` (honest, not overclaimed).
- **Surfaces**: the `run_python_strategy` agent tool (used from the chatbot) +
  `POST /quant/python/run`; reference strategies in `quant/examples/`
  (`ma_crossover`, `mean_reversion`, `vol_target_trend`).

## AI Strategy Copilot (grounded, not generative of results)

The copilot's LLM proposes and explains; deterministic code computes. It uses the
SAME store/engine/validator as manual strategies and cites what it references.

- **Signals** (`calculate_signals`): the entry/exit decision timeline with reason
  codes and optional indicator snapshots — **no orders are submitted**, no
  portfolio is touched.
- **Research plan** (`create_research_plan`): hypothesis, universe, data
  requirements, IS/validation/holdout splits, benchmark, declared costs, an
  inferred parameter search space, objective, metrics, walk-forward, robustness
  checks, acceptance criteria and known biases (survivorship, overfitting,
  look-ahead). The holdout is used once, never for repeated selection.
- **Report** (`generate_strategy_report`): Markdown grounded ONLY in a stored
  experiment + its artifact — metrics, warnings, trade extremes, reproducibility
  and the "no live orders, not investment advice" note.
- **Iteration helpers**: `generate_entry_exit_rules` (plain-language rules),
  `configure_position_sizing`, `configure_stops_and_targets` (validated copies).
- **Research conveniences**: `get_experiment_status`, `cancel_experiment`,
  `calculate_performance_metrics`, `analyze_trade_log`, `compare_strategies`,
  `run_parameter_sweep`.
- **Routes**: `/quant/signals`, `/quant/strategies/{id}/research-plan`,
  `/quant/experiments/{id}/report`. Tool count: 68 `quant_*` tools (incl. the
vectorized engine, standalone cost diagnostics, out-of-sample, bootstrap,
multiple-testing, option analytics, futures continuous contracts and comparison
tools in `advanced_tools.py`). These are also exposed over REST:
`POST /quant/vectorized-backtest`, `/quant/costs`, `/quant/out-of-sample`,
`/quant/bootstrap`, `/quant/multiple-testing`, `/quant/option-price`,
`/quant/implied-volatility`, `/quant/option-strategy`, `/quant/continuous-contract`
(thin adapters over the same core functions).

Grounding is carried by the tools themselves: their outputs are deterministic
artifacts (a signal timeline, a plan, a report) or explicit typed errors, so the
model has no tool that returns a fabricated result. Reports and plans always
reference the experiment id / strategy version / seed they were built from.

## Indicators, expressions & benchmark metrics

- **Indicator library** (`indicators.py`): SMA, EMA, WMA, RMA, RSI, ATR, StdDev,
  ROC, Highest, Lowest, Bollinger, MACD, VWAP, plus **Stochastic (%K/%D), ADX
  (+DI/-DI), Donchian, Keltner, OBV, MFI, Williams %R and CCI**. All are causal
  (warm-up is NaN); each declares its outputs, so rule references resolve exactly.
- **Expression DSL** (`strategy.py` + `rules.py`): rule operands may be a
  constant, a reference, or a typed **expression** — arithmetic (`+ - * /`),
  `min`/`max`, unary `neg`/`abs`, and a causal `lag`/shift — evaluated per bar.
  Division by zero and missing operands yield no value (the condition is `False`,
  never `inf`/fabricated). Validation recurses into expressions (`UNKNOWN_REFERENCE`,
  `BAD_LAG`). The DSL is safe (no `eval`).
- **Benchmark-relative metrics** (`benchmark.py`): `analyze_against_benchmark`
  computes alpha, beta, correlation, tracking error, information ratio, and
  total/excess return from an experiment's equity curve vs a real benchmark
  series; fewer than 3 aligned observations returns `available: false` with a
  reason (never a fabricated number).

## Governance, inspection & multi-file projects

- **Approvals** (`store.request_approval`/`decide_approval`): a review gate per
  strategy version (`requested → approved|rejected`), recorded on
  `agent-memory.db` (`QuantStrategyApproval`).
- **Deployments** (`store.create_deployment`): a governed, **paper-only** record
  (`QuantStrategyDeployment`). It requires an approved version
  (`APPROVAL_REQUIRED`); `mode="live"` is refused with `LIVE_TRADING_DISABLED`
  and **no code path routes an order** — a deployment is bookkeeping, never an
  execution (`liveExecution: false`).
- **Source inspection** (`inspect_python_strategy`): a static AST pass over
  imports/third-party modules/restricted modules/dangerous calls. Explicitly
  advisory — the isolated worker is the security boundary.
- **Multi-file projects** (`run_python_project`): a `{entry, files}` project runs
  in the same isolated, env-scrubbed, time-limited worker; sibling modules import
  by name.
- **Static validation depth**: `AMBIGUOUS_FILL_TIMING` (warning) and
  `INDICATOR_TF_UNORDERED` (error) join the existing checks.

**Runtime hardening & dependency policy**: approved numerical dependencies
(`sdk_deps.py`) — `inspect_source` flags `UNAPPROVED_DEPENDENCY`, and packages are
never installed on demand. Isolation is process + scrubbed env + timeout + output
cap + POSIX `RLIMIT_CPU`/`RLIMIT_AS`, with an **optional Docker backend**
(`resolve_sandbox`/`docker_command`; `--network none --read-only --memory 512m
--cpus 1 --pids-limit 256`) used when `HARNESS_QUANT_SDK_DOCKER_IMAGE` is set and
Docker is present, else an open fallback to the process worker.

**Paper shadow loop**: `run_paper_session` runs a deployed (approved, active)
strategy as a REAL backtest over recent data and records a `QuantPaperRun`
(experiment id, metrics, status). Live order routing is absent everywhere; the
only reachable deployment mode is `paper` (`liveExecution: false`).

## Vectorized engine (fast path, restricted on purpose)

`quant/vector_engine.py` is a **restricted** fast path, not a second general
backtester. It runs only the strategy semantics that reduce to a causal
signal → target position → mark-to-market pipeline and **refuses everything
else** with a structured `VECTOR_UNSUPPORTED` error (routed to the event engine):
no protective legs, no path-dependent risk rules, no confirmation timeframes, no
execution latency, `fill_at=next_open`, sizing in {fixed_quantity, fixed_dollar,
percent_equity}, one symbol. It reuses the SAME `build_context` indicators,
`rules.evaluate`, `sizing.compute_quantity`, `ExecutionSimulator` and
`MetricsEngine`, so a supported strategy cannot silently change meaning. For the
supported subset the two engines agree **exactly** on the equity curve
(`test_quant_vector_advanced.py::test_vector_event_parity_fixed_quantity`).

## Standalone execution-cost diagnostics

`quant/costs.py` exposes the SAME cost models the engine uses as four standalone
tools — `simulate_transaction_costs`, `simulate_slippage`, `simulate_spread`,
`simulate_market_impact`. Given a list of hypothetical orders (side/quantity/price
+ optional bar context: `atr`, `avgVolume`, `barSpread`, OHLCV) and an
`execution` assumptions block, each returns a per-order audit, the total, the
model used, and warnings where a model lacked a required input (a missing input
contributes zero and is reported — never presented as a measured zero cost). It
accepts camelCase cost keys (`marketImpact`, `fillAt`, …) as well as the field
names, and a frictionless configuration is labelled `frictionless: true`.

## Out-of-sample and bootstrap

- `run_out_of_sample_test` (`quant/validation.py` + `advanced_tools.py`) resolves
  the full dataset, splits it chronologically into an in-sample head and an
  out-of-sample tail (`split_index`), runs the **real event engine** on each
  disjoint slice, and reports both metric sets plus a `leakage`/`split` block
  (`overlapBars: 0`). It persists the OOS run. It cannot itself verify that
  parameters were frozen before the window was seen, so it emits
  `OOS_PARAMETERS_MUST_BE_FROZEN` — an explicit, honest caveat, not a certification.
- `run_bootstrap_test` computes a **percentile** bootstrap CI for a return-series
  statistic (`mean`/`total`/`std`/`sharpe`) using IID, block (circular) or
  stationary resampling. It is seeded and reproducible; IID resampling warns
  `BOOTSTRAP_IID_ASSUMES_INDEPENDENCE`; block size is recorded. Input is either an
  experiment id (its equity curve is converted to per-period returns) or an
  explicit returns array. Only the experiment slice, not a fabricated distribution.
- `compare_backtests` compares stored experiments on a fixed metric set and adds
  comparability cautions when ranges/instruments/capital differ or a run is
  frictionless, so a fair ranking is never implied when assumptions differ.

## Multiple-testing & overfitting diagnostics

`quant/multiple_testing.py` (tool `run_multiple_testing_diagnostics`) implements
two referenced methods from first principles (no SciPy):

- **Deflated Sharpe Ratio** (Bailey & López de Prado, 2014) — the probability the
  selected strategy's per-period Sharpe is positive *after* deflating for the
  number of trials and the returns' skew/kurtosis. Needs the trial-Sharpe variance
  (`trialSharpes` or `srVariance`+`trialCount`); without it the result is
  `available: false` with a reason.
- **Probability of Backtest Overfitting** via Combinatorially Symmetric
  Cross-Validation (Bailey, Borwein, López de Prado & Zhu, 2016) — over all
  balanced IS/OOS partitions of a configs×periods return matrix, how often the
  in-sample best lands in the worse out-of-sample half.

The tool **runs a real bounded parameter sweep** (`strategyId` + `paramSpace`) to
build the trial Sharpes and matrix, or accepts an explicit return series / trial
Sharpes / matrix. It states its assumptions and never applies a test whose inputs
are missing. It is intentionally separate from `robustness.py` (which aggregates
stability/sample-size/regime evidence into a verdict) — neither is applied
mechanically.

## Engine selection

`run_backtest` / `run_event_driven_backtest` run the authoritative event engine;
`run_vectorized_backtest` runs the restricted vector engine and refuses
unsupported strategies. Both produce the same `BacktestResult` envelope, tagged
`metadata.engine` (`event-driven` | `vectorized`).

## Capability state (never overclaimed)

`BacktestResult.capability` and `GET /quant/capabilities` report:

```
available    stocks, crypto, fx, multi-symbol, multi-timeframe,
             commission, slippage, spread (incl. historical), latency, market-impact,
             strategies, experiments, indicators, metrics, portfolio-backtest,
             optimization (grid/random/evolutionary/bayesian), walk-forward,
             monte-carlo, sensitivity, robustness, graph-compiler,
             vectorized-backtest (restricted subset), cost-diagnostics,
             out-of-sample, bootstrap, backtest-comparison, multiple-testing,
             option-pricing/greeks/implied-vol, multi-leg option strategy analytics,
             continuous futures contracts
partial      futures (continuous-contract construction yes; backtest trades the
             continuous PROXY, not deliverables),
             options (pricing/Greeks/IV/strategy analytics + live chains yes;
             historical options BACKTESTING no),
             python-strategies (isolated worker process; not a container)
unsupported  — (nothing advertised unavailable that is implemented)
```

Capabilities not listed are **not registered as tools** and are advertised
unavailable rather than faked.

## Options & futures analytics

`quant/options.py` and `quant/futures.py` fill the last asset-class gaps. Options
**pricing does not get re-implemented**: they reuse `market.greeks.black_scholes`
(the one options model) and add:

- `price_option` — theoretical price + Greeks (assumptions stated with the result);
- `implied_volatility` — the inverse of Black-Scholes by bisection, refusing prices
  outside the no-arbitrage bounds so it never returns a fabricated vol;
- `analyze_option_strategy` — multi-leg expiry payoff curve, net premium,
  break-evens, and **max profit/loss reported `null` when unbounded** (never a
  fabricated grid maximum), plus position-level net Greeks (× multiplier).

`build_continuous_contract` splices ordered futures contracts at a roll schedule
with `difference` / `ratio` back-adjustment (or `none`), records every roll (date,
contracts, gap, factor), leaves the newest contract unadjusted, and labels the
result an explicit backtest **proxy**. Option **backtesting** and deliverable
futures contracts are deliberately not claimed.

## Research engines

- **Optimization** (`optimize.py`): grid, random, evolutionary, and Bayesian
  (GP-EI) search over a `params.ParamSpace` of dotted strategy paths. Objectives
  are oriented higher-is-better (`max_drawdown` negated, `return_drawdown` =
  CAGR/|DD|). Multi-objective runs return a Pareto front. Results carry the
  leaderboard, per-axis parameter **stability**, and warnings for low sample size
  and raw-return objectives — the engine never presents the highest raw return as
  the winner by default.
- **Walk-forward** (`walkforward.py`): rolls train→test windows; parameters are
  optimized **only** on the training slice (a test that mutates test-only bars
  asserts the chosen params do not move), then evaluated on the unseen test
  slice. Reports in-sample / out-of-sample / combined and the IS→OOS divergence.
- **Monte-Carlo** (`montecarlo.py`): trade reshuffle, return bootstrap, parameter
  perturbation, execution perturbation; percentiles, probability of loss/ruin,
  expected/worst drawdown; seeded and reproducible.
- **Sensitivity / robustness** (`robustness.py`): one-at-a-time parameter sweeps
  (best value, collapse, stability), cost sensitivity, trade concentration,
  sample size and regime dependence combine into a deterministic verdict
  (`robust` / `fragile` / `insufficient_evidence`) with plain-language
  conclusions derived from measured evidence.

## Relationship to the Portfolio Accounting Engine

`harness/portfolio/` is the ledger for **real holdings** (long-only, Decimal,
tax lots, FIFO/LIFO/average cost). `quant/portfolio.py` is the **backtest
simulation** portfolio (long/short, float, bar-level mark-to-market). They are
deliberately separate because the accounting core refuses shorts (a required
trading capability) and is tax-lot oriented rather than tick-loop oriented. For
long-only runs the two MUST agree on realized P&L; this is asserted by
`python/tests/test_quant_portfolio_sizing_risk.py::test_reconciles_with_portfolio_accounting_engine_long_only`.
Wiring short-capable strategies into the ledger is deferred and would be an
extension of the accounting core, not a fork (see ADR-H150).

## Production notes

**Live market-data path.** The engine reads bars through the ONE Market Data
Gateway. Two fixes make real history actually loadable: `_fetch_provider` now
forwards each provider's OWN ticker (`providerSymbols`, so `BTC-USD` → `BTCUSDT`
for Binance instead of asking Binance for a pair it does not trade), and
intraday crypto (`1m`…`4h`) prefers Binance over the yfinance/stooq adapters
that collapse intraday bars to a calendar date. Covered by
`python/tests/test_market_intraday_routing.py`.

**Background execution.** Backtests and research runs accept `background: true`
on their POST body; the work is submitted to `quant/runner.py` (an asyncio task
behind a concurrency semaphore) and the caller polls
`GET /quant/runs/{id}[/cancel]`. The runner reports a stage + percent
(optimization reports evaluated/total, Monte-Carlo reports simulations, etc.),
supports cancellation, and retains the result in memory for an hour (the durable
copy is the experiment artifact). The Backtest UI has a "Run in background"
toggle and polls the same endpoints. Heavy runs therefore never block the
request loop.

**Performance.** Indicators are O(n) and the engine is a single pass over the
merged timeline; `python/tests/test_quant_performance.py` guards against an
accidental quadratic (a 5000-bar/eight-indicator backtest runs in well under a
second, asserted under a generous 20s ceiling).

## Extending it

- **New indicator**: add to `INDICATOR_CATALOG` + `compute_one` in
  `indicators.py`; validation picks it up automatically.
- **New data provider**: it must be declared on the TS market bridge
  (`src/lib/harness/market/providers/`) mapped to the `market_data` capability;
  the Python engine only ever calls the gateway.
- **New sizing/risk/cost method**: extend the corresponding model + engine.

## Deferred (documented, not hidden)

**Options analytics are now available** (`options.py`: pricing, implied vol,
Greeks, multi-leg strategy payoff/risk) and the live options-chain/greeks surface
lives in the market layer (`market.greeks`, `get_options_chain`). Two things are
deliberately still not claimed and are advertised `partial`:

- **historical options backtesting** — needs dated option chains and expiry
  handling in the event engine; the analytics tools do not pretend otherwise;
- **deliverable futures contracts** — `build_continuous_contract` produces an
  explicit backtest *proxy* (back-adjusted continuous series), not a physically
  settleable contract.

Everything else in the required tool list has a working, tested engine behind it.

Heavy runs are offloaded in-process (see **Background execution** above), so a
long backtest/optimization no longer blocks the request. Deeper scaling — a
distributed worker pool or the harness job scheduler hosting quant targets with
cross-process persistence — is a later step; today background runs are bounded
by the process lifetime and retained in memory for an hour.

Data-quality findings from the dataset (gaps, duplicates, out-of-order,
incomplete bars) are surfaced as `DATA_*` warnings on the result; they are never
silently dropped.

**Portfolio backtests honour per-strategy assumptions.** A portfolio run shares
ONE portfolio but builds one `ExecutionSimulator` + `RiskEngine` **per strategy
binding**, so each symbol's fills and risk limits follow its own strategy's
costs/limits (a test asserts two strategies with different commission pay their
own rate).
