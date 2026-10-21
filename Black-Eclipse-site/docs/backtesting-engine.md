---
title: Backtesting & Simulation Engine — Audit, Tool Coverage & Blockers
status: Current
last-verified: 2026-10-20
---

# Backtesting & Simulation Engine — Audit, Tool Coverage & Blockers

**Who this is for:** anyone assessing what the deterministic quant engine covers,
where each requested capability lives, and what is genuinely *not* done.

This doc is the **requirements traceability matrix** for the backtesting &
simulation capability. The authoritative design lives in
`docs/quant-engine.md`; this file maps the requested capability surface to the
code that implements it and states the honest gaps. It does not re-document the
engine internals.

## Phase 0 audit result

The repository already contained a mature, deterministic **event-driven quant
engine** (`python/harness/quant/`) with: a structured strategy IR + rule DSL,
causal indicators, point-in-time datasets, order lifecycle, commission/slippage/
spread/impact models, position sizing, risk limits, a backtest portfolio ledger,
metrics with definitions, experiment persistence + gzipped artifacts, background
runs, optimization, walk-forward, Monte-Carlo, sensitivity/robustness, a Python
SDK in an isolated worker, a strategy-graph compiler, governance (approvals /
paper deployments, no live routing) and 54 agent tools. The audit's job was to
find the **genuine gaps** against the requested 16-tool surface, not to rebuild
what exists.

## The 16 requested tools — coverage

| Requested tool | Status | Implementation |
|---|---|---|
| `run_backtest` | existing | `tools.run_backtest_tool` → `engine.run_backtest` |
| `run_event_driven_backtest` | **added** | `advanced_tools.run_event_driven_backtest_tool` → event engine |
| `run_vectorized_backtest` | **added** | `vector_engine.run_vectorized_backtest` (restricted subset) |
| `run_portfolio_backtest` | existing | `tools.run_portfolio_backtest_tool` |
| `simulate_transaction_costs` | **added** | `costs.simulate_costs("transaction")` |
| `simulate_slippage` | **added** | `costs.simulate_costs("slippage")` |
| `simulate_spread` | **added** | `costs.simulate_costs("spread")` |
| `simulate_market_impact` | **added** | `costs.simulate_costs("impact")` |
| `run_parameter_sweep` | existing | `copilot_tools.run_parameter_sweep` → `optimize_parameters` |
| `run_walk_forward` | existing | `tools.run_walk_forward` |
| `run_out_of_sample_test` | **added** | `advanced_tools.run_out_of_sample_test` |
| `run_monte_carlo` | existing | `tools.run_monte_carlo` |
| `run_bootstrap_test` | **added** | `validation.bootstrap_ci` via `advanced_tools` |
| `run_sensitivity_analysis` | existing | `tools.run_sensitivity_analysis` |
| `analyze_trade_log` | existing | `copilot_tools.analyze_trade_log` |
| `compare_backtests` | **added** | `advanced_tools.compare_backtests` (+ comparability warnings) |
| `run_multiple_testing_diagnostics` (beyond the 16) | **added** | `multiple_testing.py` (Deflated Sharpe + PBO/CSCV) |
| Options: `price_option`, `implied_volatility`, `analyze_option_strategy` (beyond the 16) | **added** | `options.py` (reuses `market.greeks`) |
| Futures: `build_continuous_contract` (beyond the 16) | **added** | `futures.py` (splice + back-adjustment) |
| Regime-aware uncertainty: `run_regime_monte_carlo` (beyond the 16) | **added** | `regime.py` + `montecarlo.py` (`regime_block_bootstrap`) |
| Evidence grading: `grade_strategy_edge` (beyond the 16) | **added** | `verdict.py` (A–F verdict + overfit tells) |
| Prop-firm evaluation: `run_prop_firm_simulation`, `list_prop_firm_rules` (beyond the 16) | **added** | `propfirm.py` + `propfirm_mc.py` (real rules as data, day-level resampling) |

All 16 are registered in `quant/tools.py` (`QUANT_TOOLS`, now **72** tools) and
allowlisted automatically through `harness/agents.py`. `run_event_driven_backtest`
and `run_vectorized_backtest` carry `metadata.engine` provenance.

## Capabilities already satisfied elsewhere (evidence)

- **Point-in-time data, manifests, quality** — `quant/data.py`, `quant/datasets.py`,
  `quant/dataset_store.py`; quality findings surfaced as `DATA_*` warnings.
- **Order lifecycle, fills, partial fills, ambiguity** — `quant/orders.py`,
  `quant/execution.py`; next-bar fills, limit/stop/stop-limit/trailing/take-profit.
- **Costs as an engine-level capability, not post-processing** — `quant/execution.py`
  (`commission/slippage/spread/market_impact/latency`); the standalone `costs.py`
  tools reuse the same models.
- **Ledger & accounting invariants** — `quant/portfolio.py`; long-only runs are
  reconciled against the real Portfolio Accounting Engine by an existing test.
- **Determinism / reproducibility** — seeded RNG, content-hashed strategy versions,
  gzipped artifacts, same-input ⇒ same-output tests.
- **Parameter sweeps, trial tracking** — `quant/optimize.py`, `quant/params.py`.
- **Walk-forward / Monte-Carlo / sensitivity / robustness** — dedicated modules.
- **Durable runs, cancellation, recovery** — `quant/runner.py` (in-process) and the
  harness Execution Fabric for durable jobs.
- **Security / sandboxing** — Python strategies run in an isolated, env-scrubbed,
  time-limited worker (`sdk_runtime.py`), with optional Docker backend; approvals
  and paper-only deployments refuse `live` (`LIVE_TRADING_DISABLED`).

## Verification (this change)

- `python/tests/test_quant_costs_validation.py` — cost models (incl. square-root
  impact) + bootstrap + split.
- `python/tests/test_quant_vector_advanced.py` — capability boundaries, vectorized
  run, **exact vector/event parity**, no-look-ahead, OOS contamination detection,
  and all 10 new tools end-to-end.
- `python/tests/test_quant_multiple_testing.py` — norm helpers, DSR, PBO/CSCV.
- `python/tests/test_quant_options_futures.py` — Black-Scholes reference values,
  IV round-trip + bounds, multi-leg payoff/boundedness/Greeks, and futures
  splice/adjustment.
- `python/tests/test_quant_routes.py` — the advanced REST endpoints are registered
  and `/quant/costs` executes end-to-end.
- `python/tests/test_quant_regime_verdict.py` — the regime classifier (causality,
  label axes, refusal on too few bars), trade placement and per-regime
  attribution, the regime-block Monte-Carlo (attribution payload, seed
  reproducibility, preserve mode, refused mix) and the Edge Verdict (grade
  caps, critical flags, weight redistribution, overfit tells).
- `python/tests/test_quant_propfirm.py` — the prop-firm rules: every built-in
  spec validates and is sourced, unknown firms and unknown sizes are refused
  rather than guessed, the trailing maximum loss never moves down and locks at
  the starting balance, a daily loss limit pauses instead of failing, the
  Topstep consistency target raises the profit target instead of failing the
  account, the FTMO consistency rule is judged over the period rather than on
  day one, an access period that expires fails the evaluation while a shorter
  log is inconclusive, and the Monte-Carlo is reproducible, reports the
  outcome distribution and uses the fees it was given.
- Full Python suite: **5555 passed, 16 skipped (opt-in live), 0 failed** (full
  run); the `-k "quant or stats"` subset shows one **pre-existing, unrelated**
  `test_artifacts_api::test_stats_and_tags` ordering failure that does not appear
  in the full run.
- `npx tsc --noEmit` — clean.

## Honest remaining blockers / not-claimed

- **Options** are now `partial`: pricing, implied vol, Greeks, multi-leg strategy
  analytics and live chains are available; **historical options backtesting** is
  not (it needs dated chains + expiry handling in the event engine).
  **Futures** is `partial`: `build_continuous_contract` produces a back-adjusted
  continuous *proxy*; deliverable-contract backtesting is not claimed.
- **Vectorized engine** covers only the causal-signal subset; it refuses
  everything else. It is not a general faster engine.
- **Out-of-sample** now *detects* contamination (a prior optimization/walk-forward/
  sensitivity/robustness experiment whose window overlaps the OOS window flags
  `OOS_WINDOW_CONTAMINATED`) but still cannot see a selection done outside the
  store; it also always emits `OOS_PARAMETERS_MUST_BE_FROZEN`.
- **Market impact** is a participation model (linear or square-root); without
  volume inputs it reports zero *with a warning*, never a calibrated estimate.
- **Multiple-testing** diagnostics compute when their inputs exist; they assume
  IID-ish returns and contiguous-block dependence and say so.
- **Python strategy isolation** is process-level, not a hard container, unless the
  optional Docker backend is configured (`HARNESS_QUANT_SDK_DOCKER_IMAGE`).
