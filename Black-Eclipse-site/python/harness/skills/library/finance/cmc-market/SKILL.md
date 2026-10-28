# CoinMarketCap Market API

## Purpose

Retrieve market-wide sentiment and dominance metrics with their calculation method and window.

## When to use

- The user asks for fear and greed, BTC dominance, or global market metrics.
- A market-wide CMC chart or index is needed.

## When not to use

- Single-asset analysis.
- Exchange-specific data.

## Procedure

1. Identify the market-wide metric and its window.
2. Retrieve with the mapped Eclipse tool or CMC reference.
3. State the calculation method and update cadence.
4. Return the series in chart-ready form.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never present a sentiment index as a price forecast.
- Label delayed or sampled series.

## Output

Return the metric, series, method, and notes.

