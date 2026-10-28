# Charts

## Purpose

Render a correct, readable chart from explicit data with honest axes and units.

## When to use

- A number series needs a visual.
- A comparison or distribution is clearer as a chart.

## When not to use

- A single number that needs no visual.
- A decorative image; use `system.image-generation`.

## Procedure

1. Check that the data has consistent units and ordering.
2. Choose the chart type that fits the question.
3. Label axes, units, and the time window.
4. Render inline and keep the source series available.
5. Do not truncate an axis without marking it.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never smooth or interpolate missing points silently.
- Do not use area or 3D effects that distort magnitude.

## Output

Return the rendered chart and any data warnings.

