# Browser Use

## Purpose

Drive a visible browser session to complete a web task, taking a snapshot before acting.

## When to use

- The task needs a live page, login, or form interaction.
- A screenshot or DOM extraction is needed.

## When not to use

- A static page can be fetched with `web_extract`.
- Sites that prohibit automated access.

## Procedure

1. Navigate and snapshot the page state first.
2. Act on stable elements, not pixel guesses.
3. Verify each step before the next.
4. Capture evidence for any extracted value.
5. Stop and ask the user for credentials or consent when required.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never enter credentials without user consent.
- Do not bypass a paywall, captcha, or access control.
- Respect robots and site terms.

## Output

Return the result, screenshots, and warnings.

