# Personal Memory

## Purpose

Persist and recall durable user context without storing secrets or transient noise.

## When to use

- The user states a durable preference or fact.
- An answer depends on prior conversation context.

## When not to use

- Storing credentials, tokens, or sensitive identifiers.
- Transient task state that belongs in the job record.

## Procedure

1. Decide whether the fact is durable and user-specific.
2. Search first to avoid duplicates.
3. Write a concise, attributable memory.
4. On recall, cite the memory and its date.
5. Honour a forget request by deleting the record.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Keep secrets out of memory.
- Do not infer sensitive traits.
- Do not present a stale memory as current fact.

## Output

Return the recalled memories or the record written.

