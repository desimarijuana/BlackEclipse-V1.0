# SwiftUI Interface Engineering

## Purpose

Implement a SwiftUI screen with correct state ownership, navigation, accessibility, and adaptive layout.

## When to use

- A new SwiftUI screen or navigation flow is needed.

## When not to use

- UIKit-only work.
- The ios-apps plugin is unavailable.

## Procedure

1. Define the screen states and ownership.
2. Build the view hierarchy with adaptive layout.
3. Add accessibility labels and traits.
4. Preview across size classes and verify.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not fight the framework with manual layout where SwiftUI provides a primitive.
- Keep state ownership explicit.

## Output

Return the code, checks, and notes. Requires the ios-apps plugin.

