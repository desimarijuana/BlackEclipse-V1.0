# CoinMarketCap DEX API

## Purpose

Apply CoinMarketCap DEX endpoints to on-chain token questions and surface contract-level risk.

## When to use

- The user asks about a token by contract address.
- A rug-risk or liquidity check is needed.

## When not to use

- CEX-only market data.
- Executing a swap.

## Procedure

1. Resolve the chain and contract address first.
2. Choose the token, pool, transaction, or security endpoint.
3. Retrieve and timestamp the result.
4. Summarise liquidity, holder concentration, and security flags.
5. State what the endpoint cannot verify.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never claim a token is safe.
- Never execute an on-chain transaction.
- Require a contract address for token-specific analysis.

## Output

Return the DEX data, security flags, and notes.

