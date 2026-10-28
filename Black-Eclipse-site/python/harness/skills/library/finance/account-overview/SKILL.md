# Account Overview

## Purpose

Answer account and portfolio questions from recorded data, with the exact period and basis.

## When to use

- The user asks what they hold, their balance, or their PnL.
- Reviewing their own trade history or activity.

## When not to use

- Trading or transferring funds.
- Another person's account.

## Procedure

1. Identify the account and the requested view.
2. Read holdings, balances, and activity for the stated period.
3. Compute PnL with an explicit cost basis and currency.
4. Separate realised from unrealised results.
5. Report missing or unreconciled records.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never expose secrets or full account identifiers.
- Never invent a missing fill or balance.
- Label estimates and stale snapshots.

## Output

Return the requested account view with limitations.

