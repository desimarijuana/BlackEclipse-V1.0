# Cloud Drive

## Purpose

Find and manage cloud files through a connected drive plugin, with explicit paths and permissions.

## When to use

- The user asks to find, read, or upload a cloud file.

## When not to use

- Local workspace files.
- A drive that is not connected.

## Procedure

1. Confirm the connected account and the target drive.
2. Search by name and content, then verify the match.
3. Read or upload and record the resulting path.
4. Report permission or quota failures.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never share a private file publicly by default.
- Do not delete files without explicit approval.

## Output

Return the matched files or the document reference.

