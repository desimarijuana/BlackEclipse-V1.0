# Asset Analysis

## Purpose

Turn market and company data into a reasoned view with an explicit opposing case, risk, and optional levels. Execution is never part of this skill.

## When to use

- Buy, hold, sell, or comparison questions.
- Screens, valuation, allocation, or entry and exit planning.
- The user asks whether an asset is worth owning.

## When not to use

- Factual data lookups only; use `finance.market-data`.
- Executing an order.
- Market-wide briefings.

## Procedure

1. Resolve the instrument and venue, then confirm data coverage.
2. Gather price history, company financials, news, and relevant cross-asset context.
3. Choose an analysis frame: valuation, trend, relative strength, or risk.
4. Quantify what can be quantified; state units and periods.
5. Build the strongest opposing case before the conclusion.
6. Size the view to the user's stated risk profile and horizon.
7. If levels are requested, derive them from data and label them conditional.
8. List what would invalidate the view.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Missing data is `UNAVAILABLE`, never a reason to estimate silently.
- Never present a plan as guaranteed or as a directive.
- Eclipse forbids automated trading; never promise execution.
- Respect the user's risk tolerance without moralising.

## Output

Return JSON matching `outputSchema`, then a concise readable analysis.

