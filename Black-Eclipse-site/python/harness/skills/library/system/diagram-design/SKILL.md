# Diagram Design

## Purpose

Produce a clean, editable diagram as standalone HTML with inline SVG and a neutral visual system.

## When to use

- A process, architecture, or relationship needs a diagram.
- A document needs an explanatory figure.

## When not to use

- A quantitative chart; use `system.viz-chart`.
- A photorealistic image.

## Procedure

1. Choose the diagram type that matches the relationship.
2. Lay out nodes and edges before styling.
3. Use one visual system with consistent spacing and type.
4. Add concise labels and a legend where needed.
5. Render and check legibility at target size.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not overload a diagram with every detail.
- Keep labels readable; no overlapping text.

## Output

Return the HTML artifact and a description of the diagram.

