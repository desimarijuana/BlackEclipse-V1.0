# Strategy Discovery

## Purpose

Find published strategies that fit a goal, compare them on the same evidence, and explain the trade-offs.

## When to use

- The user asks for a strategy or a better trading approach.
- Comparing leaderboard strategies or creators.

## When not to use

- Authoring a bespoke strategy; use `finance.strategy-codegen`.
- Copying a strategy without reviewing its risk.

## Procedure

1. Clarify the goal, risk profile, venue, and horizon.
2. Search published strategies and list the plausible candidates.
3. Compare on return, drawdown, turnover, capacity, and live track record.
4. Inspect the rules and flag curve-fitting or missing costs.
5. Recommend a shortlist with the strongest counterargument.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not treat a leaderboard rank as proof of future edge.
- Distinguish live from simulated records.
- Disclose creator incentives where known.

## Output

Return the candidate list, comparison, and a reasoned shortlist.

