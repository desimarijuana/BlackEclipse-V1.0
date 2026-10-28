# Binance Web3 Reference

## Purpose

Map on-chain questions to the right Binance Web3 endpoint and state the chain and contract explicitly.

## When to use

- The user asks for on-chain candles, trending tokens, smart-money trades, holders, or liquidity pools.
- A token or wallet needs chain-level inspection.

## When not to use

- Swaps, approvals, or transaction broadcasting.
- Data that a native Eclipse market source already covers.

## Procedure

1. Resolve the chain and the contract address, not just the ticker.
2. Choose the endpoint for candles, ranking, trades, holders, pools, or wallet activity.
3. Retrieve and record the chain, contract, timestamp, and source.
4. Flag wash trading, honeypots, and thin liquidity where relevant.
5. Never treat a trending rank as a recommendation.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never broadcast a transaction or request a signing key.
- Require a contract address for token-specific claims.
- Label unverified on-chain data as such.

## Output

Return the on-chain data with chain and provenance.

