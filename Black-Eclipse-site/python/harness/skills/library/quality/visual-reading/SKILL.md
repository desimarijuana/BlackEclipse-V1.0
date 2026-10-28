# Visual Reading

## Purpose

Extract text and structure from images and scanned documents while reporting confidence and where each value came from.

## When to use

- Reading a screenshot, receipt, form, or scanned table.
- Extracting series or labels from a chart image.
- Checking whether an image supports a claim.

## When not to use

- Native text or structured data is already available.
- Generating a new image.

## Procedure

1. Load the asset and confirm its type and resolution.
2. Run OCR for literal text and visual analysis for layout, rows, and chart structure.
3. Separate observed values from inferred structure.
4. Attach a confidence and a bounding location to every extracted value.
5. Re-read ambiguous regions instead of guessing.
6. List unreadable or cropped regions explicitly.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never invent a value that OCR did not produce.
- Do not treat a chart's pixel position as an exact price without axis evidence.
- Flag rotated, cropped, or low-resolution sources.

## Output

Return JSON matching `outputSchema` plus the extracted text.

