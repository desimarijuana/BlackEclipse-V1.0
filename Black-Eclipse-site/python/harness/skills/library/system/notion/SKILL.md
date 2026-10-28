# Notion

## Purpose

Find, read, or publish a structured Notion page without flattening its blocks.

## When to use

- The user asks to search or update Notion.

## When not to use

- Local notes or a different wiki.
- Notion is not connected.

## Procedure

1. Confirm the workspace and the target page.
2. Search and read before writing.
3. Publish with the original block structure.
4. Return the page link.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not overwrite a page without a read-first.
- Respect workspace permissions.

## Output

Return the pages or the published page reference.

