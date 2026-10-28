# CoinMarketCap Exchange API

## Purpose

Answer exchange-level questions with CMC endpoints and the correct comparison basis.

## When to use

- The user asks about exchange volume, market pairs, or reserves.
- Comparing venues for integration or liquidity.

## When not to use

- Single-token price lookups.
- Account-specific exchange data.

## Procedure

1. Resolve the exchange identity; names are not unique.
2. Choose info, volume, pairs, or assets.
3. Normalise volume by quote currency and reporting window.
4. Flag wash-trading and reporting-method differences.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not compare raw volumes without normalising.
- Never present reserve data as a full audit.

## Output

Return the exchange data and comparison notes.

