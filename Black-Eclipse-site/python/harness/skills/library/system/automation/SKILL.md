# Automation

## Purpose

Create bounded, observable automations and never leave an unbounded job running silently.

## When to use

- The user asks for a reminder, recurring agent, or price alert.
- A local workflow should run on a schedule.

## When not to use

- One-off tasks that should run now.
- Automated trading, which Eclipse forbids.

## Procedure

1. Clarify the trigger, schedule, and expected output.
2. Create the job with a bounded timeout and output target.
3. Test it once with `job_run_now`.
4. Report the schedule, next run, and how to stop it.
5. List jobs so the user can audit them.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never create an automation that executes trades.
- Always provide a stop path.
- Do not schedule an unbounded scrape or loop.

## Output

Return the automation, schedule, and status.

