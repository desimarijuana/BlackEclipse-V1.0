# Brokerage Order Plan

## Purpose

Prepare a reviewable single-leg equities order and stop before execution.

## When to use

- The user wants to buy or sell a stock or ETF in a brokerage account.

## When not to use

- Multi-leg options or on-chain tokenized stocks.
- Unapproved or automated execution.

## Procedure

1. Resolve the symbol and confirm the brokerage venue.
2. Read buying power or the position being sold.
3. Preview price, fees, and order type implications.
4. Show the plan and require explicit confirmation.
5. Record the intended order only after approval.
6. Explain that Eclipse cannot submit the order.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never claim an order was submitted.
- Never bypass the preview.
- Flag illiquidity and extended-hours risk.

## Output

Return the plan, preview, risks, and approval flag.

