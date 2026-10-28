# Office File Editing

## Purpose

Make surgical edits to existing Office files while leaving everything else byte-stable where possible.

## When to use

- An existing DOCX, XLSX, PPTX, or PDF needs a targeted change.

## When not to use

- Creating a new file from scratch.
- A format the document tool cannot parse.

## Procedure

1. Open and inspect the package structure before editing.
2. Change only the requested parts.
3. Preserve styles, relationships, and embedded media.
4. Verify the file opens and the edit is present.
5. List any feature that could not be preserved.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never rebuild the whole file when a targeted edit is possible.
- Keep a backup of the original.

## Output

Return the edited file, changes, and unsupported features.

