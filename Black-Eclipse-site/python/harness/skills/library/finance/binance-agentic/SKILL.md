# Binance Agentic Account

## Purpose

Surface Binance account and market context through the connected plugin, with clear provenance and no order placement.

## When to use

- The user asks about a Binance sub-account or Binance-specific market data.
- Spot, margin, convert, or futures context is needed.

## When not to use

- Placing or cancelling orders.
- Venues other than a connected Binance account.

## Procedure

1. Confirm the plugin connection and the selected sub-account.
2. Read the requested view and label it with its timestamp.
3. Reconcile balances against open orders and positions.
4. Flag permission or connection problems explicitly.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never place, cancel, or modify an order.
- Never expose credentials.
- Mark plugin failures instead of substituting invented data.

## Output

Return the requested account or market view with provenance.

