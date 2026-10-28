# Binance Market Reference

## Purpose

Answer Binance market-data questions with the correct public endpoint and the Eclipse tool that maps to it.

## When to use

- The user explicitly wants Binance or CEX spot, futures, funding, or open-interest data.
- An asset is not covered by Hyperliquid and a CEX source is needed.

## When not to use

- Order placement, account, margin, or withdrawal work.
- A non-Binance venue.

## Procedure

1. Resolve the instrument and confirm it is listed on Binance.
2. Pick the correct endpoint family: spot, USD-M, COIN-M, funding, or open interest.
3. Retrieve via the mapped Eclipse tool rather than scraping the page.
4. Record endpoint, timestamp, and units.
5. Fall back to another covered source only when Binance is unavailable.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Public market data only; never request or use account credentials.
- Do not place or manage orders.
- Report rate-limit or coverage failures honestly.

## Output

Return the data with endpoint and provenance.

