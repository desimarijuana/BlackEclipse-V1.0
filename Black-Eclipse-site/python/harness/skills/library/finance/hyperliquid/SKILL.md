# Hyperliquid Reference

## Purpose

Retrieve Hyperliquid read-only data with the correct endpoint and coin naming, and never imply order capability.

## When to use

- The user asks about Hyperliquid prices, funding, books, or positions.
- HyperEVM contract state is needed.

## When not to use

- Order placement or fund movement.
- A venue other than Hyperliquid.

## Procedure

1. Resolve the coin name in Hyperliquid's convention.
2. Choose Info, WebSocket, or HyperEVM RPC.
3. Retrieve and timestamp the result.
4. Respect rate limits and batch reads where possible.
5. State that execution is out of scope.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Read-only; never place or cancel orders.
- Never move funds.
- Do not guess a coin name.

## Output

Return the data with endpoint and rate-limit notes.

