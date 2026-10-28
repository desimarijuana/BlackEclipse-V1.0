# Calendar

## Purpose

Check availability and manage events without inventing free time.

## When to use

- The user asks about availability or wants an event created.

## When not to use

- Calendar is not connected.
- Scheduling a transaction or trade.

## Procedure

1. Confirm the calendar and timezone.
2. Read free-busy before proposing a slot.
3. Create or update only after confirmation.
4. Return the event link and timezone.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never double-book silently.
- Do not modify an event without reading it first.

## Output

Return the events or availability with timezone.

