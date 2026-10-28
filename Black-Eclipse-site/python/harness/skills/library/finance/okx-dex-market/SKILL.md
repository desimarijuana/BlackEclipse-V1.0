# OKX DEX Market Data

## Purpose

Answer OKX DEX price, candle, and wallet-PnL questions with chain and timestamp context.

## When to use

- The user wants on-chain token prices or candles.
- Wallet DEX history, win rate, or realized PnL is needed.

## When not to use

- Writing a WebSocket bot; use `finance.okx-dex-ws`.
- CEX-only market data.

## Procedure

1. Resolve chain, token, and wallet explicitly.
2. Choose price, candles, index, or wallet PnL.
3. Retrieve and timestamp the data.
4. Separate realized from unrealized PnL.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never fabricate a wallet history.
- Label index prices as model-based.

## Output

Return the data, PnL breakdown, and provenance.

