# SwiftUI Performance Diagnostics

## Purpose

Find the actual cause of a SwiftUI performance problem with repeatable measurements.

## When to use

- Scrolling stutters, launches are slow, or views update too often.

## When not to use

- Speculative optimisation without a symptom.
- The ios-apps plugin is unavailable.

## Procedure

1. Reproduce the symptom and capture a baseline.
2. Profile view updates, layout, and rendering.
3. Identify the dominant cost.
4. Apply one fix and re-measure.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not claim an improvement without before and after numbers.
- Prefer the smallest structural fix.

## Output

Return measurements, cause, fix, and checks. Requires the ios-apps plugin.

