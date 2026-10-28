# PDF Documents

## Purpose

Produce or manipulate PDF files and verify page count and text extraction.

## When to use

- The user asks for a PDF or wants existing PDFs merged, split, or watermarked.
- A PDF needs reading or text extraction.

## When not to use

- Editable Word or spreadsheet output.
- Image-only slides.

## Procedure

1. Confirm the action and the source files.
2. Create or transform the PDF and record the output path.
3. Verify page count, file size, and text extraction.
4. For scans, run OCR and label low-confidence regions.
5. Report any failed file explicitly.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not claim a PDF exists before verifying it.
- Preserve the originals when splitting or watermarking.

## Output

Return the PDF reference, page count, and extracted text when requested.

