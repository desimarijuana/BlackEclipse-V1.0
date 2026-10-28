# Proactive Mandates

## Purpose

Translate a theme and risk budget into a concrete allocation proposal with stress tests, then route it for approval.

## When to use

- The user wants a managed, themed portfolio.
- An existing mandate needs review or rebalancing.

## When not to use

- Single-asset analysis.
- Unapproved portfolio changes.

## Procedure

1. Define the theme, budget, constraints, and risk profile.
2. Construct candidate allocations and optimise within constraints.
3. Run stress tests and show downside scenarios.
4. Present the proposal with trade-offs and assumptions.
5. Route for explicit approval; do not implement.
6. Record the approved mandate and its review cadence.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never implement an unapproved mandate.
- Never hide concentration or liquidity risk.
- Do not imply guaranteed returns.

## Output

Return the mandate, proposal, stress test, and approval status.

