# iOS App Intents

## Purpose

Design App Intents that expose the right actions and entities without leaking app internals.

## When to use

- The user adds Siri, Shortcuts, Spotlight, or App Intent support.

## When not to use

- Non-Apple platforms.
- The ios-apps plugin is unavailable.

## Procedure

1. Define the entity, action, and parameter surface.
2. Implement the intent and its query.
3. Add App Shortcuts phrases.
4. Build and test in Simulator or on device.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Follow current Apple APIs; avoid deprecated intent patterns.
- Do not expose destructive actions without confirmation.

## Output

Return the intent design, code, and verification checks. Requires the ios-apps plugin.

