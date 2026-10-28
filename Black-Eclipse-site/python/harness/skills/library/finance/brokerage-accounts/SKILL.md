# Brokerage Accounts

## Purpose

Give a read-only, reconciled view of connected brokerage accounts.

## When to use

- The user asks what a brokerage account holds.
- Cash, buying power, positions, or open orders are needed.

## When not to use

- Placing or cancelling brokerage orders.
- On-chain tokenized equities.

## Procedure

1. List connected accounts and resolve the requested one.
2. Read the requested view and timestamp it.
3. Reconcile positions against orders and activities.
4. Report any connection or permission gap.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Read-only: never place or cancel orders.
- Never expose account credentials.
- Do not infer positions from stale data.

## Output

Return the requested account view with warnings.

