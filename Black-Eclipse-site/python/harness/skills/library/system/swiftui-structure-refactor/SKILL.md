# SwiftUI Structure Refactor

## Purpose

Split an oversized SwiftUI view without changing behavior or leaking state across boundaries.

## When to use

- A view is too large to reason about.
- State or navigation ownership needs cleanup.

## When not to use

- A behavior change is the actual goal.
- The ios-apps plugin is unavailable.

## Procedure

1. Record current behavior and state ownership.
2. Extract cohesive subviews and move state deliberately.
3. Keep previews and tests working.
4. Verify the behavior is unchanged.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not change behavior while refactoring.
- Do not spread state across unrelated views.

## Output

Return the changes and behavior-preservation checks. Requires the ios-apps plugin.

