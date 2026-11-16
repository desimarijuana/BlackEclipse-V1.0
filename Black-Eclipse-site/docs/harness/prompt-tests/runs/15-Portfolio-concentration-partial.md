# 15. Portfolio concentration partial

- runId: `run_f8df372d-331a-4149-93f9-4f53c8a71cf3`
- status: **completed**
- steps: 24 / tools: 29 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:28:17.183Z / finishedAt: 2026-11-16T21:32:46.344Z

## Prompt

Analyze my portfolio's concentration and produce a rebalance proposal. If a price is missing, mark it and show the rest.

## Answer

## I can't produce the rebalance â and the reason is the one you anticipated

I read the portfolio and every price leg came back empty. Here is exactly what the engine holds, all figures as of this run (2026-11-16, 21:28 UTC).

| Item | Value | Status |
|---|---|---|
| Portfolio | UwU Portfolio (`pf_7586246984d44b11bfb8`), base currency PKR, FIFO | verified |
| Open positions | 5 | verified |
| Cash | **-29,922.56 PKR** | verified |
| Total value | **-29,922.56 PKR** | verified |
| Position market value | **0.00** (total equals cash exactly) | inferred: prices missing |
| Data quality flag | `PARTIAL` | verified |
| Tax-loss harvest candidates | 0 (threshold: any loss â¥ 1 PKR) | verified |
| Reconciliation vs a 5-symbol external list | `MISSING 5, matched 0` | verified |

Two consequences follow directly:

1. **Concentration is undefined.** If all five holdings carry zero market value, the denominator for every weight is cash alone (and a negative one at that). Computing "the largest position is X% of the book" off that would produce a >100% cash weight and negative position weights â arithmetic that reconciles to nothing real. I won't print it.
2. **A rebalance proposal is unformable.** `portfolio_rebalance` takes explicit target weights and converts them into buy/sell amounts using the current symbol quantities and prices. With neither leg readable, any buy/sell instruction would be invented. I also did not get symbol-level output from the portfolio read: my attempts to pull positions, allocation and exposure returned only the one-line summary above (and one attempt timed out at the tool boundary).

The negative cash with zero-valued holdings is the signature of an unpriced book rather than a portfolio that is genuinely short PKR 29.9k â but treat that as a diagnosis, not a measurement. It is also why the harvest scan returned zero candidates: unrealised loss needs a price to exist.

## What is needed to finish

Three specific gaps, in the order that unblocks the most:

- **Symbols + quantities for the five holdings.** The portfolio read kept returning only the summary line. This is the single missing fact â everything else follows from it.
- **A PKR price per symbol.** This is the PSX coverage gap I've hit before on this market: Pakistani micro-cap and small-cap tickers frequently have no vault quote. Once symbols are known, PSX quotes or the company pages can be worked one name at a time and each figure labelled by provenance.
- **Cash of -29,922.56 PKR resolved.** Either a deposit/funding entry is missing from the ledger, or a position's quantity is overstated. `portfolio_rebuild` recomputes derived lots and materialised positions from the transaction journal â running it is the cheapest first check, since the journal itself is intact even when valuation is not.

## The proposal shape, ready to fill in

So that nothing is lost in translation, this is the framework I will apply the moment the quantities and prices exist. It is a plan, not a recommendation:

- **Concentration screen** â per-name weight, top-1 and top-3 share, and the Herfindahl index $HHI=\sum_i w_i^2$ (a 5-name equal-weight book scores 0.20; a single 50% name pushes it past 0.30).
- **Cap rule** â trim any name above a stated ceiling (most commonly 25% per name, 35% top-3) back to the ceiling, redirecting proceeds to the underweights first and cash second.
- **Turnover budget** â cap total traded value so a concentration fix doesn't become a cost event; the engine returns estimated fees and tax impact per plan, and PKR brokerage plus the PSX transaction levy both enter it.
- **Before/after concentration pair** â the same HHI and top-3 share computed on the post-trade book, so the improvement is measured rather than asserted.

Send me the five symbols (or re-run the portfolio read so the positions surface) and I will price what can be priced, mark the rest UNAVAILABLE, and deliver the weights, the concentration numbers and the buy/sell lines together. One caution worth stating now: of your 29 portfolios, most are USD duplicates of Core Growth / Dividend Income / Tech Satellite / PSX Value, and the only other PKR book â Chodh Fund â holds zero positions. I analysed UwU because it is the only PKR portfolio with holdings; if you meant one of the USD books, say which and I'll redirect.

Advisory note: the following recommendation(s) are not backed by a portfolio calculation or a consulted source, so they are unverified advice, not verified analysis: short PKR.
