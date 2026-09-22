# Research Planning

## Purpose

Convert a user's financial research objective into a **structured research
plan** that names the questions to answer, the data required, the evidence
strategy, and the expected deliverables — before any analysis is attempted.

## When to use

- A research request is broad, multi-part, or under-specified.
- The user asks "how would you go about researching X".
- A larger analysis needs its scope fixed first.
- You must decide which data/tools are even relevant.

## When not to use

- The request is a single, precise data lookup (call the retrieval tool).
- The user has already supplied a complete, unambiguous plan.
- The task is a report of already-gathered research (use report generation).

## Required inputs

| Input | Required | Meaning |
|---|---|---|
| `objective` | yes | The research question in the user's words. |
| `instruments` | no | Tickers/names the objective concerns. |
| `market` | no | Venue, when known. |
| `horizon` | no | Time period/horizon. |
| `constraints` | no | User-supplied constraints. |

If `instruments` is omitted and the objective implies a specific instrument,
state that resolving the instrument is a **preparatory step** — do not guess a
ticker.

## Required context

- Whether the objective is about a company, a sector, a macro theme, or a
  market-wide event.
- Any market/venue the user named. Never assume a default venue.

## Procedure

1. Restate the `objective` faithfully. Do not silently broaden or narrow it.
2. Decompose it into 3–7 concrete `questions` that must be answered. Each
   question must be answerable by evidence, not opinion.
3. For each question, list the `requiredData`: the data type, the instrument or
   series, the period, and whether a structured source or web evidence is
   appropriate. Use the retrieval vocabulary (`current_quote`,
   `historical_prices`, `financial_statements`, `macro_series`, `news`,
   `web_research`).
4. Build the `sourcePlan`: for each data need, the preferred source **tier**
   (structured vault/provider, official/primary document, reputable secondary).
   Never name a provider the runtime does not have.
5. Fix the `period` (reporting periods, date ranges) explicitly.
6. List `risksAndUncertainties`: what could be missing, stale, ambiguous, or
   conflicting — including instrument-identity ambiguity and coverage gaps.
7. State `expectedDeliverables` (e.g. "a fundamental summary with reported
   figures and citations", "a comparison table", "a risk list").
8. Record `assumptions` separately from facts. Assumptions are never evidence.

## Tool usage rules

- Use `research_search` / `research_search_news` only if a preliminary source
  landscape is genuinely needed. Planning is mostly reasoning, not retrieval.
- Never call a tool to "confirm" a plan; tools produce evidence, not plans.

## Evidence requirements

A plan contains **no measured facts**. Do not present a plan entry as if it
were retrieved data. Any instrument identifier named in the plan must be
carried as "to be resolved", not asserted.

## Validation rules

- `objective` is non-empty and matches what the user asked.
- `questions` has at least one entry; each is answerable by evidence.
- `requiredData` entries name a data type and period.
- `sourcePlan` entries reference source **tiers**, not invented providers.
- `expectedDeliverables` is non-empty.

## Output requirements

Return JSON matching `outputSchema`. Keep `assumptions` explicit. Do not
fabricate figures, dates, or citations in a plan.

## Known limitations

- The planner does not know whether a specific dataset exists until retrieval is
  attempted; the `sourcePlan` is a strategy, not a guarantee of availability.
- Coverage differs by market — a plan for an uncovered market must say so.

## Failure handling

- If the objective is too ambiguous to plan (e.g. "research it"), return a plan
  whose first question is a clarification request, and mark the uncertainty.
- Never fill a missing period or instrument with an invented value.

## Example

Objective: "Is ACME a good long-term buy?"
Questions: profitability trend, cash generation, debt load, valuation vs peers,
key risks.
requiredData: financial statements (3–5y), historical prices, company profile.
sourcePlan: structured financials first; primary filings for segment detail;
reputable secondary only for context.
risksAndUncertainties: fiscal-period alignment, currency, share class.
expectedDeliverables: a fundamental summary with reported figures + citations,
and an explicit limitations list.
