# iOS Xcode Workflow

## Purpose

Run the Xcode build and test loop and report failures with the actual diagnostic text.

## When to use

- An iOS project must be built, tested, or launched.

## When not to use

- Non-Apple projects.
- The ios-apps plugin is unavailable.

## Procedure

1. Resolve the project, scheme, and destination.
2. Build and capture the first diagnostic.
3. Run tests and summarise failures by suite.
4. Launch the app and verify it starts.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not claim a green build without the exit status.
- Fix the root cause, not the test.

## Output

Return build and test status with diagnostics. Requires the ios-apps plugin.

