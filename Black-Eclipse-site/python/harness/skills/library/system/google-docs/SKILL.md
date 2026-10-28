# Google Docs

## Purpose

Read or write a Google Doc while preserving its structure and sharing model.

## When to use

- The user asks to read or update a Google Doc.

## When not to use

- A local DOCX deliverable.
- Google Workspace is not connected.

## Procedure

1. Confirm the document and the requested change.
2. Read the current content before editing.
3. Apply the update and record the revision.
4. Return the document link.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not change sharing permissions implicitly.
- Do not overwrite unrelated sections.

## Output

Return the document reference and changes.

