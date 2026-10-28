# Google Sheets

## Purpose

Read or write Google Sheets with explicit ranges and no silent schema changes.

## When to use

- The user asks to read or update a Google Sheet.

## When not to use

- A local XLSX deliverable.
- Google Workspace is not connected.

## Procedure

1. Confirm the spreadsheet and range.
2. Read the header and existing values first.
3. Apply the change and verify the affected range.
4. Return the sheet link.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never clear a range without approval.
- Do not change formulas silently.

## Output

Return the sheet reference and row count.

