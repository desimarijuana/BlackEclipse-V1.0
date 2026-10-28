# Computer Use

## Purpose

Complete a desktop task through the accessibility tree, escalating to foreground control only when required.

## When to use

- No API exists and a desktop app must be operated.
- The user explicitly asks for GUI automation.

## When not to use

- A CLI or API can do the job.
- Unattended control of sensitive apps.

## Procedure

1. Identify the target window and read the accessibility tree.
2. Prefer element indices over coordinates.
3. Act one step at a time and verify the result.
4. Escalate to foreground only when the driver requires it.
5. Stop before any destructive or financial action.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never click through a destructive confirmation without approval.
- Do not type credentials into an unknown window.
- Leave the machine in a usable state.

## Output

Return the result, action log, and warnings.

