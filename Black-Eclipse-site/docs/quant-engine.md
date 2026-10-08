---
title: Quant Engine — Trading, Backtesting & Research
status: Current
last-verified: 2026-10-08
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
| Parameter spaces (dotted paths, ranges, grid/sample) | `quant/params.py` |
| Optimization (grid/random/evolutionary/Bayesian, objectives, Pareto, stability) | `quant/optimize.py` |
| Walk-forward (train/test, IS/OOS/combined, divergence) | `quant/walkforward.py` |
| Monte-Carlo (reshuffle/bootstrap/parameter/execution perturbation) | `quant/montecarlo.py` |
| Sensitivity + robustness + overfitting safeguards | `quant/robustness.py` |
| Shared research-result envelope | `quant/research.py` |
| Strategy + experiment persistence, artifacts | `quant/store.py` |
| Golden synthetic datasets | `quant/fixtures.py` |
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
   earlier bar, (2) advance trailing stops, (3) trigger protective legs, (4)
   evaluate exit signals, (5) evaluate entry signals at the close, (6) snapshot.
   Nothing computed from bar `i` fills an order on bar `i`.
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
- Market impact: `none | linear`.
- Latency: `latency_bars`.
- A filled `Fill.price` already embeds slippage/spread/impact adversely; those
  components are reported for audit but only `commission` is charged separately
  to cash. A frictionless run only ever results from an explicit `none`
  configuration (`ExecutionAssumptions.is_frictionless`).

## Reproducibility & experiments

Each experiment stores the full envelope: strategy id+version, symbols,
interval, range, initial capital, random seed, engine version, execution
assumptions and metrics. Metadata lives in the ONE `agent-memory.db` connection
(additive, idempotent DDL); the large result series (equity/drawdown/trades/
orders/fills) are written as gzipped JSON artifacts under
`.black-eclipse/quant/experiments/`. Same inputs + same seed ⇒ identical result.

## Capability state (never overclaimed)

`BacktestResult.capability` and `GET /quant/capabilities` report:

```
available    stocks, crypto, fx, multi-symbol, multi-timeframe,
             commission, slippage, spread (incl. historical), latency, market-impact,
             strategies, experiments, indicators, metrics, portfolio-backtest,
             optimization (grid/random/evolutionary/bayesian), walk-forward,
             monte-carlo, sensitivity, robustness
partial      futures
unsupported  options
```

The `unsupported` items are **not registered as tools** — they are later phases
and are advertised as unavailable rather than faked. Options remain Phase 7.

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

## Extending it

- **New indicator**: add to `INDICATOR_CATALOG` + `compute_one` in
  `indicators.py`; validation picks it up automatically.
- **New data provider**: it must be declared on the TS market bridge
  (`src/lib/harness/market/providers/`) mapped to the `market_data` capability;
  the Python engine only ever calls the gateway.
- **New sizing/risk/cost method**: extend the corresponding model + engine.

## Deferred (documented, not hidden)

**Options (Phase 7) remain deferred** and are advertised `unsupported` (not
registered as tools): a real options abstraction (contracts, pricing, IV,
Greeks, option strategies) is its own build and is not faked. `futures` is
`partial`. Everything else in the required tool list now has a working,
tested engine behind it.

Backtests currently run **in-request** (the `run_backtest` tool declares a
bounded `long_running` budget; the HTTP proxy uses a 300s timeout). The
harness job scheduler (`python/harness/jobs/`) only runs `skill`/`objective`
targets and has no job-level progress/cancel, so offloading very large
backtests/optimizations to a background job is a later hardening step (it would
add a job target kind + progress/cancel surface). It is documented here rather
than faked: today a run that exceeds the bound fails honestly.

Data-quality findings from the dataset (gaps, duplicates, out-of-order,
incomplete bars) are surfaced as `DATA_*` warnings on the result; they are never
silently dropped.

**Portfolio backtests honour per-strategy assumptions.** A portfolio run shares
ONE portfolio but builds one `ExecutionSimulator` + `RiskEngine` **per strategy
binding**, so each symbol's fills and risk limits follow its own strategy's
costs/limits (a test asserts two strategies with different commission pay their
own rate).
