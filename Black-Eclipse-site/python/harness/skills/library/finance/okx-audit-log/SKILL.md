# OKX Audit Log

## Purpose

Help the user locate and export OKX audit logs without conflating them with wallet balances or trading.

## When to use

- The user asks for audit logs or command history.
- A compliance export is needed.

## When not to use

- Wallet balances, swaps, or on-chain operations.
- General OKX market data.

## Procedure

1. Confirm the requested action: export, locate, or inspect.
2. Identify the log location and format for the user's platform.
3. Explain the time window and fields available.
4. Never request credentials in chat.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Logs may contain sensitive data; handle them carefully.
- Do not fabricate log entries.

## Output

Return the location, format, and any exported entries.

