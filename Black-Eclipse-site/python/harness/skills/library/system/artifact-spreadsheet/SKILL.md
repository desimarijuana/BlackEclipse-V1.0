# Spreadsheets

## Purpose

Create or audit tabular artifacts with correct types, formulas, and a documented schema.

## When to use

- The user asks for Excel, CSV, or a data table deliverable.
- An existing workbook needs auditing or conversion.

## When not to use

- Prose reports or slide decks.
- Financial statement modeling; use `finance.financial-modeling`.

## Procedure

1. Confirm the schema, units, and row count.
2. Create or edit the workbook and preserve untouched sheets.
3. Audit for blank keys, mixed types, and duplicate rows.
4. Verify formulas and totals against the source.
5. Report the file path and any unresolved issue.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never overwrite source data without a backup.
- Do not fabricate rows to satisfy a schema.

## Output

Return the workbook reference, row count, and audit issues.

