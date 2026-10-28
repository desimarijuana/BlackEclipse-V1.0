# CoinGecko Reference

## Purpose

Answer CoinGecko and GeckoTerminal questions and route data retrieval to the right endpoint or Eclipse tool.

## When to use

- The user asks about crypto prices, DeFi, NFTs, or on-chain pools via CoinGecko.
- API key, rate-limit, or authentication guidance is needed.

## When not to use

- A native market tool already covers the request.
- Trading or wallet operations.

## Procedure

1. Identify whether the question is coin-level, exchange-level, or on-chain.
2. Select the endpoint and parameters.
3. Map to an Eclipse tool when one exists; otherwise cite the API reference.
4. State rate limits and plan constraints.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never expose an API key.
- Do not present cached data as live.

## Output

Return the answer, endpoints, parameters, and notes.

