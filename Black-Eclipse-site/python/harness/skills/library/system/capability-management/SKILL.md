# Capability Management

## Purpose

Find the right capability and walk through a safe install or diagnosis without guessing.

## When to use

- The user wants to connect an app, messaging channel, skill, or MCP server.
- An integration is installed but not working.

## When not to use

- The capability is already available and working.
- Installing untrusted code without review.

## Procedure

1. Identify whether the need is a plugin, skill, or MCP server.
2. Search the catalog and inspect permissions before installing.
3. Install or configure with the narrowest scope.
4. Verify health and run a minimal test.
5. Document how to remove it.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never install an unreviewed package from an untrusted source.
- Do not grant broader permissions than requested.
- Keep secrets out of logs and chat.

## Output

Return the capability, status, and setup steps.

