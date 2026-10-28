# iOS Simulator QA

## Purpose

Exercise an iOS app flow in Simulator and report observable defects with evidence.

## When to use

- A UI flow needs verification or a screenshot.
- A crash or layout bug needs simulator evidence.

## When not to use

- A real-device-only capability.
- The simulator plugin is unavailable.

## Procedure

1. Launch the app and capture the baseline screen.
2. Walk the flow using accessibility targets.
3. Capture screenshots and logs at each failure.
4. Reproduce once before reporting.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not report a defect without a reproducible step sequence.
- Do not modify app data destructively.

## Output

Return screenshots, findings, and logs. Requires the ios-apps plugin.

