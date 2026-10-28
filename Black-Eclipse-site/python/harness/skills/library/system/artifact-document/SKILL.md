# Word Documents

## Purpose

Produce or revise a real DOCX while preserving structure, styles, and unmodified parts.

## When to use

- The user asks for a Word document, memo, proposal, or weekly report.
- An existing DOCX needs reading, summarising, or editing.

## When not to use

- PDF, slide deck, or spreadsheet output.
- Plain Markdown notes; use `system.workspace-writing`.

## Procedure

1. Read the source or brief and confirm the required sections.
2. Create or edit through `document_create`; never fake a DOCX with a text block.
3. Preserve styles, headings, tables, and images that were not changed.
4. Verify the file opens and the content matches the brief.
5. Report the file path and any unsupported feature.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not claim a file was delivered before verifying it.
- Never silently drop existing content during an edit.

## Output

Return the document reference and a short change or content summary.

