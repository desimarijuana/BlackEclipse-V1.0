---
title: Non-Bar Assets — the Irregular Cash-Flow Spine
status: Current
last-verified: 2026-11-20
---

# Non-Bar Assets — the Irregular Cash-Flow Spine

Some holdings have no daily bar: a private fund, a structured note, a rental
property, a bond bought at issue. Their value arrives as **irregular dated flows**,
and the only honest return is money-weighted.

`python/harness/entities/cashflow.py` is that spine.

## The sign convention (enforced, not documented)

Every amount is from the **holder's** point of view:

```
amount > 0   cash IN   (distribution, dividend, coupon, proceeds, redemption)
amount < 0   cash OUT  (capital_call, purchase, fee, subscription)
```

`KIND_DIRECTION` is the table, and `CashFlow.__post_init__` **rejects** a positive
`capital_call` or a negative `distribution`. Callers reliably invert statements,
so the check exists to catch that at construction rather than inside a return
calculation six layers away. A genuinely two-directional movement gets its own
`kind` (`adjustment`, `recallable_distribution`, `rebate`, `fx`, `flow`) — the
escape hatch is naming the flow honestly, never disabling the check. An unknown
kind is refused.

## Valuations are not cash

A NAV mark is a valuation, not a settled movement. It is representable
(`is_valuation=True`) because a terminal NAV is needed for IRR/TVPI, but it is
**excluded from `total()`**, `invested()` and `distributed()`. Counting it would
count the same money twice.

## The numbers

| Call | Meaning |
|---|---|
| `series.total()` | net settled cash (valuations excluded) |
| `series.invested()` / `distributed()` | gross out / gross in |
| `series.tvpi()` | distributed ÷ invested; `None` when nothing is invested (undefined, not infinite) |
| `xirr(flows)` | annualised money-weighted return by bisection over `[-0.9999, 10]`, ACT/365 |
| `series.money_weighted_return(terminal_value=…, as_of=…)` | XIRR including a terminal NAV |

`xirr` returns `None` — never a fabricated `0` — when there are fewer than two
flows or no sign change. Regular-period IRR for a NAV series stays in
`portfolio/performance.py`; this module is the dated, irregular counterpart and
does not duplicate that solver.

## Not built yet

Importers from broker/fund statements (`ingest`), fund-level `DPI`/`RVPI`
reporting, and a Prisma/`JDdS` table for persisted series. The model and maths are
the foundation those need.
