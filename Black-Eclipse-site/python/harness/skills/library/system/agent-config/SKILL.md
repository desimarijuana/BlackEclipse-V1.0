# Agent Configuration

## Purpose

Read or change runtime settings precisely, and handle credentials through the secure path only.

## When to use

- The user asks about a runtime setting, limit, or API key.

## When not to use

- Application code configuration.
- Changing a policy without the user's consent.

## Procedure

1. Read the current value before proposing a change.
2. Explain the effect and any safety limit.
3. Apply only the requested change.
4. For a credential, direct the user to the secure entry surface; never echo the value.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never print, log, or store a secret in chat.
- Never raise a safety limit without explicit consent.

## Output

Return the current settings and the exact change applied.

