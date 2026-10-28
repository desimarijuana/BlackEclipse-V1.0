# Deep Research

## Purpose

Synthesise evidence across independent sources to explain a field, compare alternatives, and surface gaps. Evidence comes first; the narrative is assembled from it.

## When to use

- Landscape studies, competitive comparisons, and literature reviews.
- A decision needs more than a single lookup.
- The user asks what the state of a field is or wants alternatives compared in depth.

## When not to use

- Routine price, quote, or single-fact lookups.
- Formatting an existing result into a document.
- A question answerable from one authoritative source.

## Procedure

1. Restate the question and define scope. Ask only when scope materially changes the answer.
2. Check `get_research_health` and `get_source_health` before trusting a source.
3. Collect evidence from independent sources with `web_search`, `web_extract`, and `get_news`.
4. Record source, URL, publication time, retrieval time, and confidence for each claim.
5. Group findings by theme and compare alternatives on the same criteria.
6. State conflicts explicitly; never average them away.
7. List gaps and what evidence would close them.
8. Write the summary last, from the assembled evidence.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Do not treat one blog post as consensus.
- Keep reported, derived, estimated, and unverified claims distinct.

## Output

Return JSON matching `outputSchema`, then a readable synthesis with inline evidence references.

