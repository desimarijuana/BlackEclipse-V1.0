# Market Data

## Purpose

Return factual market data with timestamp, source, and units. This skill retrieves and verifies; it does not recommend.

## When to use

- Price, quote, volume, market cap, history, company financials, or news lookups.
- Cross-asset snapshots for crypto, equities, FX, indices, or commodities.
- Derivatives or on-chain data when a configured source covers it.

## When not to use

- Investment recommendations or trade plans; use `finance.analysis`.
- Market-wide narrative briefings; use `finance.markets-overview`.

## Procedure

1. Resolve each symbol to a canonical instrument and venue with `resolve_instrument`; stop on ambiguity.
2. Check coverage with `get_coverage` and source health with `get_source_health`.
3. Retrieve with the narrowest tool: `get_quote`, `get_market_snapshot`, `get_historical_prices`, `get_ohlcv`, `get_fundamentals`, `get_news`.
4. Record retrieval time, source, currency, and units for every value.
5. Mark anything not covered as `UNAVAILABLE`; never estimate it.
6. Run `verify_market_data` on values used for a decision.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never label stale data as live.
- Do not present one provider's value as universal truth.
- MCP-sourced values are external and not Eclipse-verified.

## Output

Return JSON matching `outputSchema` with data first and caveats second.

