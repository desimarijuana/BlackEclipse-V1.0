# OKX DeFi Portfolio

## Purpose

Summarise DeFi positions and their protocol exposure with clear sourcing.

## When to use

- The user asks what DeFi positions they hold.
- Staking or lending exposure needs a review.

## When not to use

- Deposit, redeem, or claim operations.
- Wallet token balances unrelated to DeFi.

## Procedure

1. Confirm the wallet or account and the requested view.
2. Read positions per protocol and aggregate by asset.
3. Flag illiquid, locked, or leveraged positions.
4. State the valuation source and timestamp.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Read-only; never deposit, redeem, or claim.
- Do not fabricate a protocol position.

## Output

Return positions, protocol breakdown, and warnings.

