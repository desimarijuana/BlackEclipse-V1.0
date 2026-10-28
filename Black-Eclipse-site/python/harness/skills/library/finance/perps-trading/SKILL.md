# Perpetuals Plan

## Purpose

Produce a complete perpetuals trade plan with funding, leverage, liquidation distance, and invalidation. Execution is out of scope.

## When to use

- The user wants a long or short perpetual idea.
- Comparing venues, funding, or leverage.

## When not to use

- Spot-only purchases.
- Automated or unattended trading.

## Procedure

1. Confirm the contract exists on the chosen venue and resolve its specification.
2. Read price, funding, open interest, and orderbook depth.
3. Size the position and compute the liquidation distance.
4. State funding cost over the intended holding period.
5. Define entry, stop, and take-profit rules.
6. Ask for explicit approval; do not execute.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never imply liquidation is impossible.
- Never recommend maximum leverage.
- Never claim a position was opened.

## Output

Return the plan with liquidation distance, funding, and risks.

