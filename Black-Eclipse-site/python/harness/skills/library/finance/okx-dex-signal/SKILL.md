# OKX DEX Signals

## Purpose

Track notable on-chain wallets and aggregated buy signals while keeping the evidence and its limits visible.

## When to use

- The user asks what smart money or whales are buying.
- A KOL or custom address needs tracking.
- A trader leaderboard is requested.

## When not to use

- CEX order flow.
- Treating a signal as an automatic trade.

## Procedure

1. Resolve the address or token and its chain.
2. Choose address tracker, aggregated signal, or leaderboard.
3. Retrieve the raw activity, not only the label.
4. Check whether the signal is buy-only and how it was aggregated.
5. State lag, sample size, and survivorship limits.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never present a signal as a recommendation.
- Beware wash trading and spoofed labels.
- Label the data source and delay.

## Output

Return signals, addresses, evidence, and warnings.

