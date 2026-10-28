# Fact Finding

## Purpose

Resolve one specific claim by tracing it to primary evidence, then report a verdict with the evidence that supports or contradicts it.

## When to use

- Verifying a rumor, quote, statistic, or paper finding.
- Locating the original source behind a secondary report.
- Reconciling conflicting accounts of the same event.

## When not to use

- Broad landscape research; use `research.deep-research`.
- Ordinary market data retrieval.
- Forecast or opinion questions with no factual claim.

## Procedure

1. Normalise the claim into a testable statement.
2. Search for the earliest or most primary source, not the most popular retelling.
3. Prefer filings, official releases, datasets, and peer-reviewed work.
4. Use `claim_verify` and `citation_validate` to check attribution and quotation accuracy.
5. Record source, URL, date, and exactly what it supports.
6. Assign a verdict: supported, partly_supported, unsupported, or unresolved.
7. State the remaining uncertainty instead of forcing a binary answer.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Absence of evidence is not proof of falsehood; say `unresolved`.
- Never cite a source you did not open.
- Do not upgrade a secondary report to primary evidence.

## Output

Return JSON matching `outputSchema` plus a short evidence trail.

