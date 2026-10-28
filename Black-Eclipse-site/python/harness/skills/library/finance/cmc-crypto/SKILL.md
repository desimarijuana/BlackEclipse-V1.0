# CoinMarketCap Crypto API

## Purpose

Explain and apply CoinMarketCap cryptocurrency endpoints when the user is building an integration or needs CMC-specific data.

## When to use

- The user mentions the CMC API or a programmatic price integration.
- CMC-specific listings, trending, or category data is required.

## When not to use

- A native market tool already answers the question.
- Non-crypto market data.

## Procedure

1. Identify the required endpoint and its parameters.
2. Map it to the closest Eclipse tool; use web retrieval only for documentation.
3. State rate limits, pagination, and authentication requirements.
4. Return the data shape and an example request.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never expose an API key.
- Do not invent endpoint parameters.

## Output

Return the endpoint, parameters, data, and integration notes.

