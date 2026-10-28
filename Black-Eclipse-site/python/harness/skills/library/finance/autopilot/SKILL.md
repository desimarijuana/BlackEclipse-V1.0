# Autopilot Strategies

## Purpose

Give an accurate view of deployed strategies and their performance, and prepare lifecycle actions for approval.

## When to use

- The user asks what strategies are running or stopped.
- Performance, drawdown, or exposure of a deployed strategy is needed.
- A strategy should be paused or stopped.

## When not to use

- Authoring a new strategy; use `finance.strategy-codegen`.
- Unapproved lifecycle changes.

## Procedure

1. List deployments and resolve the requested strategy.
2. Read status, history, and account impact.
3. Summarise performance with the exact window and benchmark.
4. Flag concentration, drawdown, and funding risk.
5. Prepare any stop or pause action for explicit approval.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never stop or start a live strategy without approval.
- Never report performance without its window and basis.
- Distinguish simulated from live results.

## Output

Return the strategy list or detail with performance and risks.

