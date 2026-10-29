---
title: Financial Modeling (3-statement, DCF, LBO, comps)
status: Current
last-verified: 2026-10-28
---

# Financial Modeling

**Code:** `python/harness/modeling/`
**Tools:** `financial_model_build`, `financial_model_audit`
**Tests:** `python/tests/test_modeling.py`

## What it is

A deterministic model engine that composes the existing financial calculators
(`finance_facts/metrics.py`, `finance_facts/valuation.py`) rather than
reimplementing them. It produces a `ModelResult` with named sections, every
check, warnings and provenance, and exports a formula-bearing Excel workbook.

The model spec is closed and validated. A missing input is refused by name
(`INPUT_UNAVAILABLE`); no rate, margin or cash flow is defaulted.

## Kinds

| `kind` | What it builds |
|---|---|
| `three_statement` | Integrated income statement, cash flow, balance sheet and debt schedule with balance/CF/debt checks |
| `dcf` | Three-statement projections, FCFF, WACC and DCF over `finance_facts.valuation`, plus sensitivity |
| `lbo` | Sources & uses, debt tranches, cash sweep, exit equity, IRR/MOIC and entry×exit sensitivity |
| `comps` | Explicit peer set, EV/multiple table, percentile statistics and implied valuation range |
| `integrated` | Three-statement plus whichever of DCF/LBO/comps the spec supplies |

For an `integrated` model, a DCF is built when `assumptions.wacc` (or
`assumptions.waccInputs`, or a top-level `dcf.wacc`) is present. WACC fields accept
snake_case or camelCase (`market_cap`/`marketCap`); `comps.target` and peer rows
accept both `net_debt`/`netDebt`, `shares`/`sharesOutstanding`, `debt`/`totalDebt`
and `net_income`/`netIncome`. Duplicate statement checks are collapsed when the
DCF/LBO/comps results are merged into an integrated model.

## Spec shape

```json
{
  "kind": "dcf",
  "company": { "name": "...", "ticker": "...", "currency": "USD", "units": "millions" },
  "history": {
    "years": ["2024"],
    "series": {
      "revenue": [1000], "ebitda": [200], "da": [50], "capex": [60],
      "nwc": [100], "cash": [80], "debt": [400], "other_liabilities": [50],
      "equity": [430], "net_ppe": [600], "goodwill": [100], "shares": [100]
    }
  },
  "assumptions": {
    "forecastYears": 3,
    "revenueGrowth": [0.10, 0.08, 0.06],
    "ebitdaMargin": [0.20, 0.21, 0.22],
    "taxRate": 0.25, "interestRate": 0.06,
    "daPctRevenue": 0.05, "capexPctRevenue": 0.06, "nwcPctRevenue": 0.10,
    "debtRepaymentPct": 0.05, "dividendPayout": 0.20,
    "terminalGrowth": 0.025, "netDebt": 320, "sharesOutstanding": 100,
    "wacc": { "market_cap": 5000, "total_debt": 400, "risk_free_rate": 0.04,
              "beta": 1.1, "equity_risk_premium": 0.055,
              "cost_of_debt": 0.06, "tax_rate": 0.25 }
  }
}
```

`history.facts` is also accepted: each fact carries `metric`, `value`, `period`
and (ideally) `source`; the latest period is used.

## Engine invariants

- **Three-statement:** assets = liabilities + equity, cash flow ties to the cash
  balance, debt schedule ties, forecast revenue is positive, cash does not go
  negative. Interest is on the beginning debt balance in v1, so no iterative
  circular solve is hidden; a requested cash sweep is reported as not modelled.
- **DCF:** WACC and DCF come from `finance_facts.valuation`; the enterprise-value
  bridge (PV explicit + PV terminal) is checked; a DCF output is an ESTIMATE.
  `assumptions.midYear` discounts explicit FCF at `t + 0.5` and labels the
  convention in the warnings.
- **LBO:** sources = uses, no debt tranche goes negative, exit equity is positive,
  IRR is solved from dated sponsor cash flows. Management rollover is a separate
  equity contribution; exit proceeds split pro rata (or by
  `lbo.managementExitShare`), and sponsor IRR/MOIC use only the sponsor's share.
- **Comps:** a peer with a missing/non-positive denominator is excluded with a
  reason; the valid peer count and provenance are reported; implied ranges use
  the 25th/median/75th multiples. `comps.fx` (or a peer `fxRate`) translates
  non-target currencies. A peer with `quarterly` periods is calendarized by
  summing the four quarters ending at the target fiscal year end
  (`calendarizationMethod: "quarterly_ttm"`). Without complete quarterly data the
  peer must supply an explicit `calendarizationFactor`
  (`calendarizationMethod: "explicit_factor"`); otherwise it is excluded with a
  reason. The engine never derives an approximation.

## Workbook

`financial_model_build` writes a NEW workbook through `ArtifactService` (category
`financial`) and a JSON spec/summary artifact.

- `Cover` — company, kind, currency, checks verdict, spec hash.
- `Assumptions` — the exact input cells the model formulas reference.
- `Three Statement` — live A1 formulas (revenue growth, margins, schedules,
  balance check) plus the history column.
- `Values` — the engine's computed values for non-calculating viewers.
- `Checks` — every check with PASS/FAIL/WARN and detail.
- `Warnings`.
- `fullCalcOnLoad` / `forceFullCalc` are set so Excel recalculates on open.
  Eclipse does not claim to have recalculated a user-edited workbook.

## LBO financing

`lbo.debtTranches[]` may carry `pik: true` with a `pikRate`; the accrual is added
to the tranche balance and remains in exit debt. `revolverCapacity`,
`revolverRate` and `minimumCash` add a revolver: a cash shortfall first draws the
revolver (up to capacity), mandatory amortization is paid, and only cash above
the minimum is swept. The debt schedule reports each tranche, the revolver and
total debt; a shortfall that exhausts capacity is a warning, never a negative
cash balance presented as clean.

## Production behavior

- **Idempotent builds.** Each deliverable is registered with
  `model:<specHash>:<format>` and the spec JSON with `model:<specHash>:spec`, so a
  retried build returns the existing artifacts instead of duplicating them.
- **No invented inputs.** Missing history/assumptions/WACC/terminal inputs,
  non-positive shares, unresolved circularity and non-balancing statements are
  named failures, not repaired numbers.
- **Bridge peer retrieval is read-only.** `comps.peerSymbols` uses
  `market_snapshot` + `financial_statements`; a peer without a usable price or
  share count is excluded with a note.
- **Bounded models.** Forecast years, peers, table rows and export sections are
  capped; the workbook and reports are written only through the Artifact Center.
- **Checks are a gate, not a caption.** The summary exposes every PASS/FAIL/WARN
  and the key computed metrics (`enterpriseValue`, `equityValue`, `valuePerShare`,
  `wacc`, `irr`, `moic` where applicable), including for an `integrated` model; a
  model with a FAIL is still returned for inspection but is clearly marked.

## Deliverables

`financial_model_build` accepts `formats: ["xlsx", "pdf", "docx", "pptx"]` and
registers every requested file in the Artifact Center. The PDF/Word memo contains
the executive summary, key outputs, bounded section tables, checks and warnings.
The PowerPoint deck contains a cover, executive summary, one table slide per
section and a checks slide.

## Comps peers

`comps.peers` may be supplied explicitly, or `comps.peerSymbols` may name tickers:
`financial_model_build` resolves each through the same read-only market bridge as
every other market tool (`market_snapshot` + `financial_statements`). A peer with
no usable price or share count is excluded with a note; the engine never invents
a peer set or a missing financial value.

## Honest limits

- LBO accepts an explicit `ebitdaProjection` or derives EBITDA/capex/D&A/ΔNWC from
  the three-statement.
- The Excel workbook is the editable model; the PDF/Word/PowerPoint files are
  presentational deliverables, not recalculating models.
- Calendarization requires either complete `quarterly` periods for the target date
  or an explicit peer `calendarizationFactor`; otherwise the peer is excluded.
