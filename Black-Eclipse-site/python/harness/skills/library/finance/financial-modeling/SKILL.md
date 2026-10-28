# Financial Modeling

## Purpose

Produce auditable financial models where every projection traces to a stated assumption and every historical figure to a source.

## When to use

- A valuation, merger, LBO, or debt model is requested.
- An existing model needs to be rolled forward or audited.

## When not to use

- A quick ratio summary.
- A recommendation with no model.

## Procedure

1. Resolve the company and retrieve the historical statements.
2. State every driver and assumption before calculating.
3. Build the statements so the balance sheet balances.
4. Run the requested valuation or transaction structure.
5. Add sensitivity tables for the key drivers.
6. Audit for circularity, sign errors, and double counting.
7. List data gaps and model limitations.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never hard-code a plug to force a balance.
- Never present a valuation as a fact.
- Distinguish reported historicals from projected assumptions.

## Output

Return the model structure, assumptions, sensitivity, and limitations.

