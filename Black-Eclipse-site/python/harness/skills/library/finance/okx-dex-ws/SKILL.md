# OKX DEX WebSocket

## Purpose

Help the user run and manage an OKX on-chain WebSocket session without inventing a second streaming runtime.

## When to use

- The user wants real-time on-chain data or a WebSocket session.
- A custom streaming script needs the correct channel names.

## When not to use

- One-off historical lookups.
- A non-OKX stream.

## Procedure

1. Confirm the channels and the session lifetime.
2. Start or resume the session and set an idle timeout.
3. Poll events and summarise them in bounded batches.
4. Stop the session cleanly when done.
5. Record the channel set and any reconnect behaviour.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never leave an unbounded stream running silently.
- Bound event volume before summarising.
- Do not fabricate real-time events.

## Output

Return the session state, channels, and bounded events.

