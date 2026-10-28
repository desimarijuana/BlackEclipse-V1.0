# BTC Halving Cycle

## Purpose

Place Bitcoin in its halving cycle using observable data, and show how prior-cycle gains have decayed. This is context, not a forecast.

## When to use

- The user asks where Bitcoin is in the cycle.
- Long-horizon Bitcoin framing is relevant.
- Comparing the current drawdown and recovery to prior cycles.

## When not to use

- Short-term trading signals.
- Price targets presented as certainties.

## Procedure

1. Retrieve BTC price history and the current block-height context.
2. Compute days since the last halving and the estimated next halving.
3. Measure drawdown and recovery against prior cycles on the same basis.
4. Show gain decay per cycle with the exact windows used.
5. Report the rainbow band as a range, never a precise target.
6. State limitations: small sample, changing market structure, ETF flows.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never claim a cycle top or bottom is certain.
- Never extrapolate a prior cycle mechanically.
- Label every model and its assumptions.

## Output

Return JSON matching `outputSchema` plus a short chart-ready summary.

