---
title: Portfolio Accounting Engine
status: Current
last-verified: 2026-10-15
---

# Portfolio Accounting Engine

**Who this is for:** anyone changing portfolio behaviour, adding a portfolio
tool, or reasoning about where a portfolio number comes from.

The engine turns a **transaction ledger** into positions, valuation, P&L,
exposure, allocation, performance, risk and rebalancing proposals. The ledger is
the source of truth; every other number is derived and reproducible.

```
Transactions ──▶ Tax lots ──▶ Positions ──▶ Valuation ──▶ P&L
                                          ──▶ Exposure ──▶ Allocation
                                          ──▶ Performance ──▶ Risk ──▶ Rebalancing
```

## Where it lives

- **Runtime (authoritative):** `python/harness/portfolio/` — the accounting core
  and the service the agent tools and HTTP routes share.
- **Persistence:** the ONE `agent-memory.db` connection (see “Database” below),
  through `PortfolioStore`.
- **Agent tools:** `python/harness/portfolio/tools.py` (registered on the shared
  `ToolRegistry`).
- **HTTP:** `python/harness/routers/portfolio.py` (`/portfolio/*`, operator-gated).
- **Front door:** `src/lib/harness/portfolio-client.ts`,
  `src/app/api/portfolio/[[...path]]/route.ts`,
  `src/components/screens/portfolio/portfolio-ledger.tsx`.
- **Tests:** `python/tests/test_portfolio_*.py`.

## Source of truth

The **immutable transaction ledger**. `add_position` records a BUY; it never
runs `UPDATE position SET quantity = …`. `remove_position` records a real SELL
whose tax lots are matched to compute realized P&L. `update_position` appends an
auditable `ADJUSTMENT` — history is never rewritten; a correction carries
who/what/when/why (see `PortfolioAuditEvent`).

Positions are **derived**. `TaxLot` and `TaxLotMatch` rows are rebuilt from the
ledger whenever a mutation touches a symbol and are never edited directly. They
exist for audit and tax queries.

**One source of truth for the UI.** The Portfolio screen previously had TWO books:
the default view read a `localStorage` fund ledger while the Ledger view read
this engine, so "what are my holdings" had two answers. `migrate-to-engine.ts`
now mirrors the legacy book into the engine once (idempotent, with a
`fund.id → portfolioId` map and a rollback-safe flag), and the screen prefers the
engine view once it holds data. The engine is authoritative; there is no second
book.

### Surfacing a portfolio on a UI page (Ledger widgets)

A page widget reads a portfolio through the UI runtime's data-source string, not
by triggering the one-shot migration. The exact, parseable form is:

```
portfolio:<portfolio_id>:<view>
```

where `<portfolio_id>` is the engine id (from `GET /portfolio/list` or the
`portfolio_*` tools, e.g. `pf_7586246984d44b11bfb8`) and `<view>` is one of:

| view | engine read |
|---|---|
| `summary` | totals: value, cost basis, P&L, cash |
| `positions` | open positions (quantity, cost, value) |
| `holdings` | positions with pricing/valuation detail |
| `transactions` | the transaction ledger |
| `pnl` | realised/unrealised P&L (e.g. today's) |
| `performance` | NAV/returns time series |
| `risk` | volatility, beta, drawdown, risk contribution |
| `allocation` | weights by symbol |
| `tax-lots` | open tax lots per symbol |

Example: `portfolio:pf_7586246984d44b11bfb8:positions`.

The runtime advertises these strings via
`get_capabilities()["dataSourceRegistry"]` (and the `ui_get_capabilities` tool)
and validates them with `catalog.portfolio_source(id, view)` /
`catalog.parse_portfolio_source(source)`. The rendered components are the host
`data-table` (config `source`, or `portfolioId`) and `metric-card` (config
`metric`/`source` + `portfolioId`); a single metric adds a field suffix, e.g.
`portfolio:pf_7586246984d44b11bfb8:summary.totalValue`. The render path is the
UI data-source resolver (`src/lib/workspace/data-source.ts`) over the front
door's read routes (`/api/portfolio/{id}/query`, `/history`, `/tax-lots`);
`portfolio.positions` / `portfolio.totalValue` are **not** valid source strings —
only the colon form above resolves.

The engine's `POST /portfolio/{id}/bridge` is **not** part of this read path: it
is a write that moves a quantity of one symbol out and the bridged quantity of
another in across chains at the carried cost basis (no gain/loss), and is
exposed for cross-chain custody transfers only.

## Database

Portfolio tables live in **`agent-memory.db`** (Python-owned), not `jdds.db`:

- `jdds.db` (Prisma) is the committed **market-data** seed vault. Portfolio
  transactions are private user/agent state that must never be committed or
  treated as market data.
- Every other runtime subsystem (runs, browser, jobs, documents, market
  snapshots) persists on `agent-memory.db` via the ONE `AgentMemoryStore`
  connection with idempotent DDL. The portfolio store follows that pattern —
  no second database, no migration step.

Tables (created idempotently by `store.py`): `Portfolio`, `PortfolioAccount`,
`PortfolioTransaction`, `PortfolioPolicy`, `TaxLot`, `TaxLotMatch`,
`PortfolioPositionMeta`, `PortfolioBenchmark`, `PortfolioSnapshot`,
`RebalancePlan`, `RebalanceRecommendation`, `PortfolioAuditEvent`. Money and
quantity are stored as exact decimal **strings**; foreign keys cascade.

### Idempotency

`PortfolioTransaction` has a partial unique index on
`(portfolioId, source, externalId) WHERE externalId IS NOT NULL`. A retried
import (API/worker/network) returns the existing row instead of duplicating it.
Rows with no `externalId` are intentionally not deduplicated.

## Cost-basis methods

`FIFO`, `LIFO`, `AVERAGE_COST`, `HIFO` and `SPECIFIC_ID` are real accounting
implementations (`accounting.py`), each tested for fees, fractional quantities,
partial and complete liquidation, splits and transfers. `HIFO` consumes the
highest-cost lot first (tax-loss harvesting); `SPECIFIC_ID` consumes the exact
lots named in the sell transaction's `lot_selection` (`[{lotId, quantity}]`),
falling back to FIFO for any unselected remainder.

Golden case — BUY 10 @ $100, BUY 10 @ $200, SELL 10 @ $300:

| method | realized cost basis | realized P&L |
|---|---|---|
| FIFO | $1,000 | $2,000 |
| LIFO | $2,000 | $1,000 |
| AVERAGE_COST | $1,500 | $1,500 |

Fees on a BUY raise cost basis; fees/taxes on a SELL reduce proceeds. An
in-kind `TRANSFER_OUT` with no stated price moves at **book value** (basis
carries, no gain). Splits/reverse splits scale lot quantity and inverse-scale
per-unit cost.

**Invariants** (tested): `acquired − disposed == remaining` and
`remaining cost basis + realized cost basis == acquisition cost`. A disposal can
never drive a position negative — **short positions are refused**, not
miscalculated.

## Valuation, FX and data quality

`quantity × price`, converted to the portfolio base currency via the market
data gateway's FX. Every price is a `Mark` carrying **price, timestamp, source
and freshness** (`FRESH`/`STALE`/`VERY_STALE`/`MISSING`). A missing price or FX
yields an explicit `UNAVAILABLE`/`PARTIAL` data-quality state with named
`missingPrices` / `stalePrices` / `missingFX` — never a silently substituted
zero. Prices are read through the **Market Data Gateway** (provider-independent),
or caller-injected `marks` (the HTTP front door passes live JDdS quotes).

## P&L, exposure, allocation

- **P&L:** realized (from lot matches) / unrealized / total, plus by-symbol.
- **Exposure:** gross, net, long, short by asset / asset class / sector /
  currency / country (factor exposure is a future dimension).
- **Allocation:** by asset / asset class / sector / currency, returning absolute
  value + weight and a reconciliation check (weights ≈ 100%).

All money is `Decimal` (`money.py`); no binary float touches a balance.

## Risk (deterministic)

`risk.py`: annualized volatility, Sharpe, Sortino, max drawdown, VaR/CVaR
(historical, parametric, and a **seeded** Monte-Carlo — reproducible, not fake),
beta, correlation and concentration (HHI). Requires price history; returns
`UNAVAILABLE` with reasons when inputs are insufficient.

## Portfolio Construction & Risk Engine

Beyond the accounting core, the package carries a full construction and risk
layer. Everything is deterministic, validated and proposal-only.

- **Estimation** (`estimation.py`): expected returns (arithmetic / geometric /
  EWMA / shrinkage / user) and covariance (sample / EWMA / shrinkage /
  diagonal) computed over date-aligned returns. A covariance result carries
  symmetry / finiteness / positive-semidefiniteness / condition diagnostics and
  a documented eigenvalue-floor regularizer — an invalid matrix is reported,
  never silently replaced. Missing dates are dropped, never forward-filled to a
  fabricated zero return.
- **Construction** (`construction.py`): a shared solver path (projected gradient
  with an exact Dykstra projection onto the constraint polytope) and an
  **independent validator** that re-checks the budget, per-asset bounds,
  long-only, group/sector caps, factor caps and turnover from scratch. Methods:
  equal-weight, benchmark-weight, min-variance, mean-variance (+ efficient
  frontier), risk-parity (exact ERC via cyclical coordinate descent; custom
  risk budgets), volatility-target, Black–Litterman (Π = δΣw_mkt; absolute and
  relative views with confidence → view covariance), and factor-constrained.
  Solver status is a closed vocabulary (`OPTIMAL` … `INFEASIBLE`,
  `NUMERICAL_FAILURE`, `SOLVER_ERROR`); a result that fails independent
  validation is downgraded to `OPTIMAL_INACCURATE` and an infeasible constraint
  set returns `INFEASIBLE` with no weights — hard constraints are never silently
  relaxed.
- **Risk engine** (`risk_engine.py`): Euler risk contributions (asset- and
  group-level; Σ components = portfolio volatility; short-position signs
  preserved), plus scenario/stress testing — hypothetical symbol and factor
  shocks, historical window replay (caller-supplied point-in-time returns) and a
  seeded Monte-Carlo (VaR/CVaR). Each scenario names its assumptions.
- **Turnover & costs** (`costs.py`): one-way (`0.5·Σ|Δw|`) and gross-traded
  turnover, and a configurable cost model (commission, half-spread, impact, FX,
  minimum) that reports a missing component rather than assuming zero. A linear
  transaction-cost rate can be folded into the mean-variance / min-variance
  objective (a `transaction_cost` in the constraints payload with `current_weights`).
- **Factor-model estimation** (`estimation.estimate_factor_loadings`): per-asset
  factor loadings by OLS (with alpha, residual variance, R²). `construct` uses it
  automatically for `factor_constrained` when `factor_returns` are supplied and
  loadings are absent.
- **Factor risk model** (`estimation.estimate_factor_covariance`): builds
  Σ = B·F·Bᵀ + D (OLS loadings × factor covariance + diagonal idiosyncratic
  variance) — a genuine decomposition that does not double-count systematic and
  idiosyncratic risk. `risk_engine.factor_risk` splits portfolio volatility into
  systematic/idiosyncratic parts with factor risk contributions (Σ = systematic
  volatility). Selected with `covariance_method: "factor"` + `factor_returns`.
- **Risk caps** (`max_volatility` / `max_var`): a per-period volatility ceiling,
  enforced inside the solver as a convex penalty and independently validated. A
  parametric `max_var` (normal, at `var_confidence`) is mapped to an equivalent
  volatility cap (VaR = z·σ). An unreachable cap returns `INFEASIBLE` — never a
  silently relaxed result. Path-dependent drawdown constraints are deliberately
  NOT claimed as supported.
- **Strategy comparison** (`construction.compare_allocations`): several methods
  run over the SAME inputs and scored on the same covariance/expected-return
  yardstick (return, volatility, concentration, turnover, validation). It reports
  trade-offs; it never declares a winner.
- **Multi-period attribution** (`attribution.multi_period_attribution`): exact
  proportional geometric linking so linked effects reconcile to
  `(1+Rp)/(1+Rb) − 1`.
- **Rebalancing / walk-forward simulation** (`simulation.rebalancing_simulation`):
  a scheduled (monthly/quarterly/semiannual/annual) point-in-time simulation that
  re-estimates inputs from the trailing window at each rebalance (no look-ahead),
  drifts holdings, charges turnover and costs, and reports net performance/risk.
- **Cardinality & lot constraints** (`max_positions`, `min_position_weight`,
  `lot_size`): combinatorial, so applied as a documented post-processing step —
  drop sub-minimum positions, keep the largest `max_positions`, re-project onto
  the convex constraints, round to lot multiples — then re-validated
  independently and downgraded to `FEASIBLE_LIMIT_REACHED` (never `OPTIMAL`).
  Honest about which methods accept it.
- **Run persistence** (`store.PortfolioConstructionRun`): every construction run
  is an immutable record — method, status, symbols, target, constraints,
  independent validation, a content-hash `dataVersion` and the engine version —
  retrievable by `runId` for reproducibility after market data changes.

`PortfolioService.construct` (thin facade; flow in `construct_service.py`) can
estimate inputs from gateway history through the shared Market Data Gateway, or
accept explicit covariance/expected returns. A successful proposal is persisted
as a `PROPOSED` rebalance plan and as an immutable construction run, and always
reports `"proposal-only: no trades are placed"`.

Long simulations can run on the **Execution Fabric** (`portfolio/fabric.py`
registers a dedicated `portfolio` worker: timeout, bounded concurrency,
cancellation, progress) — submitting with `mode: "BACKGROUND"` returns a job id
rather than blocking the request.

## Performance

`performance.py`: time-weighted return, money-weighted return (IRR), CAGR,
cumulative + daily returns, and benchmark comparison (tracking error,
information ratio). Computed from portfolio snapshots.

## Rebalancing (proposal only — never executes)

`rebalance.py` produces buy/sell recommendations against target weights with
allocation before/after, estimated fees, concentration change and (when tax
rates are configured) an estimated tax impact per disposal, using the actual
lots that would be sold. Methods: `threshold`, `calendar`, `hybrid`.

> **It never writes a trade and never calls a broker.** Execution belongs to the
> Trading/Execution layer and requires explicit user approval. The result states
> `"proposal-only: no trades are placed; requires user approval"`.

Tax rules are caller-supplied (`shortTermRate`/`longTermRate`) and jurisdiction-
neutral: with no rates configured, tax impact is reported **unknown**, never
invented.

## Agent tools and safety

Registered on the shared registry with flat names (the registry rejects dotted
names):

| Tool | Class | Effect |
|---|---|---|
| `portfolio_list`, `portfolio_get` | read | — |
| `portfolio_calculate_pnl` / `_exposure` / `_allocation` / `_risk` / `_tax_lots` | read | — |
| `portfolio_reconcile`, `portfolio_list_reconciliations` | read | — |
| `portfolio_attribution`, `portfolio_factor_exposure`, `portfolio_hedge`, `portfolio_aggregate` | read | — |
| `portfolio_estimate_inputs`, `portfolio_risk_contributions`, `portfolio_stress_test`, `portfolio_transaction_costs` | read | — |
| `portfolio_compare_allocations`, `portfolio_estimate_factor_loadings`, `portfolio_simulate_rebalancing`, `portfolio_list_runs`, `portfolio_get_run`, `portfolio_factor_risk` | read | — |
| `portfolio_create` | mutating | `portfolio.write` |
| `portfolio_add_position`, `portfolio_remove_position`, `portfolio_update_position`, `portfolio_set_metadata` | mutating | `portfolio.write` |
| `portfolio_apply_corporate_action`, `portfolio_record_swap`, `portfolio_record_bridge`, `portfolio_record_reward`, `portfolio_apply_staking`, `portfolio_rebuild`, `portfolio_apply_slashing`, `portfolio_record_funding` | mutating | `portfolio.write` |
| `portfolio_rebalance`, `portfolio_optimize`, `portfolio_construct` | consequential | `portfolio.rebalance_proposal` |

Read tools run freely. Mutating and consequential tools go through the run's
effect authorizer — the `make_portfolio_authorizer` layer in
`python/harness/portfolio/authorizers.py`, composed in
`python/harness/code/authorizers.py`. Admission is not a bypass: a mutation is
authorized only by a standing grant or a single-use, digest-bound operator
approval (kind `portfolio_write`), keyed to the portfolio/workspace + tool +
canonicalized arguments, so a changed payload needs a new approval. With no
authorizer (or no matching approval) they are refused — the safe default. The
HTTP surface is operator-gated (loopback or the runtime token).

## HTTP routes

`GET /portfolio/list`, `POST /portfolio/create`, `DELETE /portfolio/{id}`,
`POST /portfolio/{id}/query` (accepts `marks`), `GET /portfolio/{id}`,
`POST /portfolio/{id}/transaction`, `POST /portfolio/{id}/position`,
`…/position/remove`, `…/position/update`, `…/metadata`,
`POST …/corporate-action`, `POST …/swap`, `POST …/bridge`, `POST …/reward`,
`POST …/staking`, `POST …/slashing`, `POST …/funding`, `POST …/rebuild`,
`GET …/tax-lots`, `POST …/reconcile`, `GET …/reconciliations`,
`POST …/optimize`, `POST …/attribution`, `POST …/factor-exposure`,
`POST …/hedge`, `POST /portfolio/aggregate`, `POST …/rebalance`,
`GET …/rebalance/plans`, `POST …/snapshot`, `GET …/snapshots`,
`GET …/history`. All operator-gated; tenant scope via the
`X-Harness-User` header (403 on mismatch).

Construction & risk routes: `POST …/construct`, `GET …/construction-runs`,
`GET /portfolio/runs/{run_id}`, `POST /portfolio/estimate-inputs`,
`POST …/stress-test`, `POST …/transaction-costs`, `POST …/compare`,
`POST …/simulate-rebalancing` (inline or `mode:"BACKGROUND"` →
`GET`/`DELETE /portfolio/simulations/{job_id}`).

## Backtesting reuse

The accounting core (`accounting.py`) is transaction-source agnostic. A future
Backtesting Engine feeds **simulated** transactions through the SAME
`compute_accounting` — no second accounting implementation.

## Corporate actions

Applied through `PortfolioService.apply_corporate_action` (tool
`portfolio_apply_corporate_action`, route `POST /portfolio/{id}/corporate-action`).
Every action appends normal ledger entries — history is never rewritten — and an
audit event. Unsupported actions are refused (`UNSUPPORTED_CORPORATE_ACTION`).

- **SPLIT / REVERSE_SPLIT** — scale lot quantity and inverse-scale per-unit cost.
- **SPIN_OFF** — the parent's cost basis is reallocated to the child by relative
  fair market value: a child acquisition (`SPIN_OFF`) plus a parent
  `COST_BASIS_ADJUSTMENT`. Basis is conserved across parent + child.
- **MERGER** — stock-for-stock carries basis (ratio → acquirer shares, basis
  carried); with cash consideration the cash boot is a real partial disposal
  (lot-matched realized gain) and the remaining basis carries to the acquirer.
- **SYMBOL_CHANGE** — an in-kind transfer pair (out at book value, in with the
  same basis) under the new symbol.
- **RIGHTS_ISSUE** — subscribe to new shares at the subscription price (an
  acquisition with cash out).
- **WARRANT_EXERCISE** — dispose the warrant at book value and acquire the
  underlying with basis = warrant basis + strike paid (the strike is a cash out).
- **RETURN_OF_CAPITAL** — reduces cost basis (non-taxable) and pays cash in; any
  excess over basis is recognized as a taxable gain via a `REALIZED_ADJUSTMENT`.

A `COST_BASIS_ADJUSTMENT` transaction (field `basis_adjustment`) reallocates
basis across open lots with no quantity change; the accounting invariant is
`acquired cost − realized cost ± Σ basis adjustments = remaining + realized`.

## Crypto

- **SWAP** (`apply_swap`, tool `portfolio_record_swap`) — a taxable disposal of
  the source asset plus an acquisition of the target at fair value (carried
  basis = net proceeds). Two ledger legs.
- **BRIDGE** (`apply_bridge`) — an in-kind cross-chain move; basis carries, no
  gain/loss.
- **Staking reward / airdrop** (`record_reward`) — an acquisition at fair market
  value.
- **STAKE / UNSTAKE** (`apply_staking`) — custody-only: audited, never changes
  quantity or basis (the engine's `PASSTHROUGH` class).
- **SLASHING** (`apply_slashing`) — a write-off: a disposal at zero proceeds,
  realizing a loss equal to the consumed basis.
- **FUNDING** (`record_funding`) — a perpetual-futures funding payment with a
  signed amount (+ received, − paid), recorded against cash.

## Attribution, optimization, factor exposure, hedging, reconciliation, aggregation

- **Performance attribution** (`attribution.py`, tool `portfolio_attribution`) —
  Brinson single-period decomposition of active return into allocation, selection
  and interaction by group (Brinson-Fachler by default, BHB optional).
- **Optimizer** (`optimizer.py`, tool `portfolio_optimize`) — real
  projected-gradient `min_variance` / `mean_variance` / `inverse_volatility` with
  exact bounded-simplex projection (long-only, per-asset bounds) and an optional
  turnover cap. Deterministic; proposal only.
- **Factor exposure** (`risk.factor_exposure`, tool `portfolio_factor_exposure`) —
  Σ weightᵢ × caller-supplied factor loadingᵢ. No loadings ⇒ unavailable.
- **P&L rollups** — `pnl.byAssetClass`, `pnl.bySector`, `pnl.byStrategy` in the
  standard read; exposure and allocation already carry every group dimension.
- **Currency hedging** (tool `portfolio_hedge`) — proposes FX hedge notional per
  non-base currency to flatten (or hit a target) exposure. Proposal only.
- **Reconciliation** (`reconciliation.py`, tool `portfolio_reconcile`) — compares
  an external statement to the ledger per symbol → MATCHED / MISMATCH / MISSING /
  UNKNOWN with an explicit tolerance; persists each run
  (`PortfolioReconciliation`). It never mutates the ledger.
- **Cross-portfolio aggregation** (tool `portfolio_aggregate`, route
  `POST /portfolio/aggregate`) — a combined view over several portfolios by id or
  owner.

## Tenant authorization

A portfolio records an `ownerId` (stamped from the creating actor). Every read
and mutation authorizes: when an actor identity is asserted and it does not match
the row's owner, the request is refused (`PORTFOLIO_FORBIDDEN` → HTTP 403).
Identity is taken from the `X-Harness-User` header (or `actorId` in a body/query),
which the Next front door forwards. When no actor is asserted the app is in its
documented single-user local mode (no authentication); an unowned row is a
legacy/guest portfolio. This is a real tenant boundary **whenever an actor is
asserted** — it does not pretend the accountless local mode is multi-user secure.

## Materialized positions

`PortfolioPosition` is a per-symbol DERIVED cache rebuilt incrementally on every
mutation, so reads price the cached rows instead of recomputing the whole ledger.
It is **never** authoritative: a missing row is recomputed from the ledger and
re-persisted on read (self-heal), and `rebuild_all`
(tool `portfolio_rebuild`, route `POST /portfolio/{id}/rebuild`) force-rebuilds
every symbol. A test asserts the cache always equals a fresh ledger recompute.

## Known limits (honest)

- **Options / derivatives pricing** is not modelled: an option/future held as a
  position is carried at cost and priced only if a market price is supplied by
  the gateway. A dedicated option-pricing/lot model is not implemented.
- **Live intraday streaming** of portfolio value is not surfaced in the UI; the
  Ledger read fetches quotes on demand.
- **Crypto validator lifecycle** (delegation, epoch rewards) is not fully
  modelled beyond the reward, slashing and custody events above.
- **Tax rules** remain caller-configured rates (jurisdiction-neutral); no
  jurisdiction tables are bundled.
- **Risk** needs enough price history; without it the report is `UNAVAILABLE`.
- **Performance** needs ≥2 snapshots; without them it is `UNAVAILABLE`.
- **Multi-user security** is enforced whenever an actor is asserted; the
  accountless local mode is intentionally NOT a multi-user boundary.
