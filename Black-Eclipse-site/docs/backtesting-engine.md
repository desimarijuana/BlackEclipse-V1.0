---
title: Backtesting & Simulation Engine — Audit, Tool Coverage & Blockers
status: Current
last-verified: 2026-10-11
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

All 16 are registered in `quant/tools.py` (`QUANT_TOOLS`, now **63** tools) and
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
- `python/tests/test_quant_routes.py` — the advanced REST endpoints are registered
  and `/quant/costs` executes end-to-end.
- Full quant + stats suite: **343 passed**, with one **pre-existing, unrelated**
  failure in `test_artifacts_api.py::test_stats_and_tags` (artifact-tag order
  dependence; passes in isolation and without these changes).
- `npx tsc --noEmit` — clean.

## Honest remaining blockers / not-claimed

- **Options** remain `unsupported` (not registered) — a real options abstraction
  (contracts, pricing, IV, Greeks) is a data- and domain-dependent build and is
  not faked. **Futures** is `partial` (contract metadata / continuous-contract
  handling needs provider support).
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
