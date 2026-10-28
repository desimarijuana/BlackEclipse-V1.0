# Image Generation

## Purpose

Create or edit an image that matches the brief, then verify the result.

## When to use

- The user asks for an image, restyle, or inpainting.
- A deck or report needs original artwork.

## When not to use

- Charts or diagrams; use `system.viz-chart` or `system.diagram-design`.
- Photorealistic claims about real people or events.

## Procedure

1. Turn the brief into a precise visual description.
2. Choose the model and aspect ratio.
3. Generate and inspect the result against the brief.
4. Revise once with a narrow correction if needed.
5. Report what the image does not depict.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not generate deceptive or impersonating imagery.
- Never claim an image is a real photograph.

## Output

Return the image reference and the final prompt.

