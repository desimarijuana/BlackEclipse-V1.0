# Data Studio Dashboard

## Purpose

Deliver a complete dashboard in one pass when the user explicitly asked for one.

## When to use

- The user says build a dashboard, market board, or monitoring page.
- A shareable data site is the requested deliverable.

## When not to use

- The user wants analysis or a chart.
- Data sources are unavailable.

## Procedure

1. Confirm the panels and the data sources.
2. Create the dashboard and populate every panel.
3. Verify the preview and the share link.
4. Report unavailable panels instead of hiding them.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not create a dashboard when a chart suffices.
- Never share private portfolio data publicly.

## Output

Return the dashboard reference, URL, and panel list.

