# Data Studio

## Purpose

Build a focused dashboard app that answers the user's question with live, sourced data.

## When to use

- The user asks for a dashboard, market board, or monitoring page.
- A repeatable data view is more useful than a one-off answer.

## When not to use

- A static chart answers the question.
- No reliable data source exists.

## Procedure

1. Clarify the decision the dashboard supports.
2. Choose the fewest panels that answer it.
3. Scaffold the app and wire each panel to a real source.
4. Add loading, empty, and unavailable states.
5. Verify the preview and log any data failure.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never ship a panel with fabricated data.
- Show data freshness on every live panel.

## Output

Return the app reference, files, and preview status.

