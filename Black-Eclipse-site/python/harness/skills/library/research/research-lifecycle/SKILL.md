# Research Lifecycle

## Purpose

Keep a live, versioned research case: evidence, thesis, assumptions, decision state, and review triggers. Each revision is additive and auditable.

## When to use

- The user wants a thesis tracked over time.
- A prior thesis needs an event-driven review.
- An investment decision needs a documented evidence trail.

## When not to use

- One-off analysis with no follow-up intent.
- Pure price alerts; use an automation.
- Order execution.

## Procedure

1. Resolve the subject identity (market, symbol, currency) before recording anything.
2. Open or create the research case and read the latest version.
3. Snapshot evidence with source, timestamp, and the change it implies.
4. Revise the thesis only when evidence warrants it; keep the prior version.
5. Record assumptions and the conditions that would falsify the thesis.
6. Define review triggers: price levels, events, filings, dates.
7. Set status to active, watchlist, closed, or invalidated.
8. Report the version number and the exact change made.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Revisions are append-only; never overwrite history.
- Do not present an old thesis as current.
- Do not convert uncertainty into a recommendation.

## Output

Return JSON matching `outputSchema` plus a concise change summary.

