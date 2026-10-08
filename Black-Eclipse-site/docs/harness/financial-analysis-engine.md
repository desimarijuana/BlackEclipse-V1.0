---
title: Financial Analysis Engine
status: Current
last-verified: 2026-10-08
---

# Financial Analysis Engine

**Who this is for:** anyone asking "where does a Sharpe ratio / DCF / growth
number come from, and why did the agent answer the way it did?"

The Financial Analysis Engine is Eclipse's **deterministic mathematical truth**
layer. The LLM decides *what* to calculate and explains the result; it never does
the arithmetic. Every number comes from a pure-Python calculator that records its
formula, inputs, assumptions and (where stochastic) its seed, so a claim is always
traceable to a reproducible computation.

It is **not** a second calculator: it extends the calculators that already existed
(`research/calculations.py`, `finance_facts/`). No formula is implemented twice.

```
Eclipse Agent (reasoning / planning / explanation)
        │  calls a finance_* tool
        ▼
research/web_tools.py            (tool contract: schema, permission, timeout)
        │
        ▼
research/finance_analysis.py     (analysis planner: compose a security/portfolio report)
        │
   ┌────┴──────────────┬───────────────────────┐
   ▼                   ▼                       ▼
research/calculations  finance_facts.metrics   finance_facts.valuation
 (risk/return series)  (ratios, growth, FCF)   (WACC, DCF, sensitivity, scenarios)
   │                   │                       │
   └───────┬───────────┴───────────┬───────────┘
           ▼                       ▼
   CalculationResult           DerivedMetric
   (formula, inputs,           (formula, inputs,
    assumptions, detail)        sources, periods)
```

## The LLM never computes the metric

```
BAD:  User: "What's Apple's Sharpe ratio?"
      LLM:  "Sharpe is approximately 1.43."      # invented arithmetic

GOOD: User → agent → finance_series(metric="sharpe", …)
              → research.calculations.sharpe (validated, deterministic)
              → result (formula + inputs + assumptions + risk-free source)
              → agent explains the returned number
```

## Calculation catalog

### Market / return series (`research/calculations.py` + `calculations_ext.py`)

| Metric | Notes |
|---|---|
| `period_change`, `cagr` | period-over-period change; compound annual growth |
| `cumulative_return`, `annualized_return` | simple or log returns (`method`) |
| `annualized_volatility` | sample stdev × √periods; configurable annualization |
| `beta` | cov(asset, benchmark)/var(benchmark) on date-aligned returns |
| `alpha` | Jensen's α = Rp − [Rf + β(Rm − Rf)], annualized; explicit Rf |
| `correlation` | pearson / spearman / kendall, date-aligned, clamped to [−1, 1] |
| `covariance` | sample (`ddof=1`) or population (`ddof=0`) |
| `sharpe`, `sortino` | explicit risk-free rate; downside deviation for Sortino |
| `value_at_risk` | historical (empirical) VaR, √time horizon scaling |
| `parametric_var` | normal VaR; the normal assumption is warned on |
| `monte_carlo_var` | **seeded**, reproducible; records simulations + distribution |
| `cvar` | expected shortfall: historical / parametric / seeded Monte-Carlo |
| `max_drawdown`, `drawdown_analysis` | scalar drawdown; full path with peak/trough/recovery dates, durations, series, top‑N |
| `rolling_volatility`, `rolling_correlation`, `rolling_beta` | rolling series in `detail` |
| `correlation_matrix`, `covariance_matrix` | date-intersection matrices |
| `risk_contribution` | Euler decomposition of portfolio volatility |

Every risk metric is a `CalculationResult` with `formula`, `inputs`,
`observationCount`, `frequency`, `annualization`, `assumptions`, `warnings`,
`detail` and a content-sensitive `calculationId`.

### Fundamentals (`finance_facts/metrics.py`)

`pe_ratio`, `forward_pe`, `peg_ratio`, `pb_ratio`, `ps_ratio`, `ev_ebitda`,
`fcf_yield`, `dividend_yield`, `roe`, `roa`, `roic`, `gross_margin`,
`operating_margin`, `net_margin`, `net_debt_to_ebitda`, `debt_to_equity`,
`free_cash_flow` (OCF − CapEx), `enterprise_value` (explicit components).

Plus `growth` with explicit basis (`yoy`/`qoq`/`mom`/`ttm`/`percent`/`cagr`) and
`free_cash_flow_to_firm` (FCFF) / `free_cash_flow_to_equity` (FCFE).

Every metric returns a `DerivedMetric` (formula + input facts + periods + sources)
and **refuses** rather than defaults when an input is missing, currencies/periods
are mixed, or the result is not economically meaningful (negative EPS P/E, ROIC
without a stated tax rate, …).

### Valuation (`finance_facts/valuation.py`)

- `wacc` — CAPM cost of equity + after-tax cost of debt; no rate is defaulted.
- `dcf` / `dcf_schedule` — per-period discounting schedule attached in `detail`.
- `dcf_sensitivity` — WACC × terminal-growth grid; cells with growth ≥ WACC are
  `None` (invalid), never a number.
- `dcf_scenarios` — named bear/base/bull (or any) scenarios from explicit
  overrides; each scenario's resolved assumptions are recorded.

`dcf_breakdown` is the **one** implementation of the discounting formula that all
DCF-shaped functions share.

## Agent tools

Registered on the one `ToolRegistry` (`research/web_tools.py`, allowlisted in
`agents.py` `WEB_RESEARCH_TOOLS`), all read-only:

| Tool | Purpose |
|---|---|
| `finance_metric_catalog` | list every metric with formula + required inputs |
| `finance_metrics` | one ratio/margin/return metric from named inputs |
| `finance_series` | one time-series metric; matrix metrics take `options.series` |
| `finance_valuation` | `wacc` / `dcf` / `dcf_sensitivity` / `dcf_scenarios` |
| `finance_growth` | explicit-basis growth (incl. CAGR) |
| `finance_fcf` | `free_cash_flow` / `fcff` / `fcfe` |
| `finance_security_analysis` | compose returns+risk+market+fundamentals+valuation |
| `finance_portfolio_analysis` | compose portfolio return/risk/matrix/risk-contribution/concentration |

The high-level tools gather nothing themselves — the caller (agent) supplies the
dated inputs it retrieved; the engine computes. A metric that cannot be computed
appears as `UNAVAILABLE` with its reason; the report carries a quality state
(`COMPLETE`/`GOOD`/`PARTIAL`/`DEGRADED`/`INVALID`).

## Determinism, provenance and reproducibility

- Same inputs + methodology + engine version ⇒ same result. `calculationId` is a
  SHA-256 digest over version, formula, inputs, window and assumptions, so
  different values for the same dates never collide.
- Monte-Carlo metrics record `simulations`, `seed`, `distribution` and the RNG
  (`random.Random`, Mersenne Twister); the same seed reproduces the same number.
- A refused metric names the missing input; a degraded one says why. Nothing is
  silently interpolated; missing observations are dropped under the recorded
  `missingDataPolicy = omit_missing_no_interpolation`.

## Testing

`python/tests/test_finance_analysis_engine.py` — known values, financial
invariants (`cov(x,x)=var(x)`, `corr∈[−1,1]`, `CVaR ≥ VaR`, components sum to
volatility), refusal paths, seed reproducibility, and the tools end-to-end. Also
`test_research_calculations.py` and `test_web_finance_quality.py`.

```
npm run test:py          # or: python -m pytest python/tests
```

## Genuine limitations

- The engine computes from **caller-supplied inputs**; it does not itself retrieve
  prices or statements. Retrieval, point-in-time enforcement and evidence
  provenance are owned by the retrieval layer / Evidence & Research Engine; this
  layer consumes their validated output.
- Parametric VaR/CVaR assume normally distributed returns (warned on every
  result). Use the historical or Monte-Carlo method when the tail is not normal.
- Rolling/matrix metrics require overlapping dates and refuse insufficient
  overlap rather than filling.
- `dcf_sensitivity` covers the Gordon-growth method only; the exit-multiple DCF
  is valued through `dcf`/`dcf_scenarios` but has no built-in multiple×metric grid.
