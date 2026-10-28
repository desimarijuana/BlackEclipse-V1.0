# Markets Overview

## Purpose

Give a compact, evidence-based cross-asset briefing: what moved, what it implies, and what remains uncertain.

## When to use

- The user asks what the market is doing.
- Daily or weekly cross-asset summaries.
- Sector rotation and risk-on or risk-off reads.

## When not to use

- Single-symbol deep analysis.
- Trade ideas with entries and exits.

## Procedure

1. Set scope: region, asset classes, horizon.
2. Pull indices, futures, FX, yields, sector performance, crypto sentiment, movers, news and earnings.
3. Compute changes against an explicit prior close or period.
4. Identify the dominant regime with evidence, not adjectives.
5. Separate drivers from coincidences; flag correlations that are not causal.
6. List upcoming catalysts and data risks.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not invent a market narrative without data behind it.
- Label delayed or partial data.
- Do not turn a briefing into a recommendation.

## Output

Return JSON matching `outputSchema` and a skimmable briefing.

