# Task Planning

## Purpose

Turn a goal into an executable plan with clear dependencies and observable acceptance checks.

## When to use

- A multi-step project needs a plan.
- Tasks need owners, ordering, or acceptance criteria.

## When not to use

- A single trivial step.
- Re-planning while the current step is still running.

## Procedure

1. Clarify the outcome and non-goals.
2. Break the work into stages with observable outputs.
3. Map dependencies and identify the critical path.
4. Define acceptance checks for each task.
5. Assign owners only where the user supplied them.
6. Track status and stop after the agreed review rounds.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not create busywork to look thorough.
- Do not mark a task done without its acceptance check.

## Output

Return the staged plan with dependencies and acceptance checks.

